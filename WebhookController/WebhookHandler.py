import json
import logging
import requests
from InitializationPackage import app
from flask import render_template, request, Response
from flask.views import MethodView
from requests import exceptions
from werkzeug.exceptions import BadRequest
from WebhookController.WebhookHelpers import WebhookHelpers


class WebhookHandler(MethodView):
    def post(self):
        logging.debug("WebhookHandler: Processing POST request.")

        cowbull_url = app.config.get("COWBULL_URL", None)
        webhook_response = {
            "speech": None,
            "displayText": None,
            "data": {},
            "source": "cowbull-agent",
            "followupEvent": {},
            "contextOut": [],
            "result": None,  # Shouldn't be here - for testing only
            "parameters": None  # Shouldn't be here - for testing only
        }

        request_data = None
        result = None
        action = None
        parameters = None

        try:
            request_data = self._post_get_json()
            helper = WebhookHelpers(game_url=cowbull_url)
            return_results = helper.perform_action(input_json=request_data)
            webhook_response["contextOut"] = return_results["contextOut"]
            webhook_response["speech"] = return_results["speech"]
            webhook_response["displayText"] = return_results["displayText"]
        except KeyError as k:
            return self._build_error_response(
                response="The key {} is missing from the JSON".format(str(k))
            )
        except Exception as e:
            return self._build_error_response(
                response="{}".format(str(e))
            )

        return Response(
            status=200,
            response=json.dumps(webhook_response),
            mimetype="application/json"
        )

    @staticmethod
    def _post_get_json():
        json_string = request.get_json(silent=True, force=True)

        if json_string is None:
            raise TypeError("No JSON was provided in the request!")

        bytesize = len(str(json_string).encode('utf-8'))
        logging.debug("WebhookHandler: JSON data processed. Loaded {} bytes".format(bytesize))

        _result = {
            "lang": json_string.get('lang', None),
            "status": json_string.get('status', None),
            "timestamp": json_string.get('timestamp', None),
            "sessionId": json_string.get('sessionId', None),
            "result": json_string.get('result', None),
            "id": json_string.get('id', None),
            "originalRequest": json_string.get('originalRequest', None)
        }

        return _result

    def oldpost(self):
        webhook_response = {
            "speech": None,
            "displayText": None,
            "data": {},
            "source": "cowbull-agent",
            "followupEvent": {},
            "contextOut": [],
            "result": None,  # Shouldn't be here - for testing only
            "parameters": None  # Shouldn't be here - for testing only
        }

        cowbull_url = app.config.get("COWBULL_URL", None)

        logging.debug("Processing webhook")
        logging.debug("Game server is {}".format(cowbull_url))

#        if not self._check_mimetype(request=request):
#            return self._build_error_response(
#                response="content-type must be explicitly specified as application/json"
#            )

        json_string = request.get_json(silent=True, force=True)

        if json_string is None:
            return self._build_error_response(
                response="No JSON was provided in the request!"
            )
        logging.debug("JSON provided was: {}".format(json_string))

        webhook_result = json_string.get('result', None)
        if webhook_result is None:
            return self._build_error_response(
                response="No result data. The request was badly formed!"
            )

        action = webhook_result.get('action', None)
        logging.debug("Processing action: {}".format(action))

        parameters = webhook_result.get('parameters', None)
        logging.debug("Parameters are: {}".format(parameters))

        contexts = webhook_result.get('contexts', None)
        logging.debug("Contexts are: {}".format(contexts))

        try:
            if action.lower() == "newgame":
                return_results = self.perform_newgame(cowbull_url=cowbull_url, parameters=parameters)
                webhook_response["contextOut"] = return_results["contextOut"]
                webhook_response["speech"] = return_results["speech"]
                webhook_response["displayText"] = return_results["displayText"]
            elif action.lower() == "makeguess":
                return_results = self.perform_makeguess(
                    cowbull_url=cowbull_url,
                    parameters=parameters,
                    contexts=contexts
                )
                webhook_response["contextOut"] = return_results["contextOut"]
                webhook_response["speech"] = return_results["speech"]
                webhook_response["displayText"] = return_results["displayText"]
        except IOError as ioe:
            return self._build_error_response(
                status_code=503,
                response="Unfortunately, the game service is unavailable: {}".format(str(ioe))
            )
        except Exception as e:
            return self._build_error_response(
                status_code=500,
                response="An exception occurred in the API webhook: {}".format(repr(e))
            )

        webhook_response["parameters"] = parameters
        webhook_response["action"] = action

        return Response(
            status=200,
            mimetype="application/json",
            response=json.dumps(webhook_response)
        )

    def perform_makeguess(self, cowbull_url=None, parameters=None, contexts=None):
        helper = WebhookHelpers(game_url=cowbull_url)

        _parameters = parameters or []
        if _parameters == []:
            raise ValueError("For some reason, no parameters are specified!")

        _contexts = contexts or []
        if _contexts == []:
            raise ValueError("For some reason, no contexts are specified!")

        key = [n["parameters"]["key"] for n in _contexts if n["name"] == "key"][0]
        digits_required = int([n["parameters"]["digits"] for n in _contexts if n["name"] == "digits"][0])
        guesses = [n["parameters"]["guesses_remaining"] for n in _contexts if n["name"] == "guesses"][0]
        digits_guessed = [int(n) for n in _parameters.get("digitlist", None)]

        guess_analysis = helper.make_guess(key=key, digits_required=digits_required, digits=digits_guessed)

        game = guess_analysis.get('game', None)
        status = game.get('status', None)
        guesses_remaining = int(game.get('guesses_remaining', 0))

        outcome = guess_analysis.get('outcome', None)
        message = outcome.get('message', None)
        analysis = outcome.get('analysis', None)
        cows = outcome.get('cows', 0)
        bulls = outcome.get('bulls', 0)

        response_text = None
        if status.lower() == "won":
            _digits_guessed_text = str(digits_guessed)
            _digits_guessed_text = _digits_guessed_text.replace('[', '').replace(']', '')
#            response_text = "Congratulations! You won the game with {}".format(_digits_guessed_text)
            response_text = message
        elif status.lower() == "lost":
            response_text = message
        else:
            message_text = ""
            for a in analysis:
                if a["match"]:
                    message_text += "{} is a bull".format(a["digit"])
                elif a["in_word"]:
                    message_text += "{} is a cow".format(a["digit"])
                else:
                    message_text += "{} is a miss".format(a["digit"])

                if a["multiple"]:
                    message_text += " and occurs more than once. "
                else:
                    message_text += ". "

            message_text += "You have {} goes remaining!".format(guesses_remaining)
            response_text = "You have {} cows and {} bulls. {}".format(cows, bulls, message_text)


        return {
            "contextOut": contexts,
            "speech": response_text,
            "displayText": response_text
        }

    def _check_mimetype(self, request):
        request_mimetype = request.headers.get('Content-Type', None)
        logging.debug("Content type of request is: {}".format(request_mimetype))

        if request_mimetype is None\
        or request_mimetype.lower() != "application/json":
            return False

        return True

    def _build_error_response(
            self,
            status_code=400,
            response=None
    ):
        logging.error(
            "HTML Status: {}; Response: {}".format(status_code, response)
        )
        webhook_response = {
            "speech": response,
            "displayText": response,
            "data": {},
            "source": "cowbull-agent",
            "followupEvent": {},
            "contextOut": [],
            "result": None,  # Shouldn't be here - for testing only
            "parameters": None  # Shouldn't be here - for testing only
        }

        return Response(
            status=status_code,
            mimetype="application/json",
            response=json.dumps(webhook_response)
        )
