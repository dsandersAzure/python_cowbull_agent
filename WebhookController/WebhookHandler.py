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
        helper = WebhookHelpers(cowbull_url=cowbull_url)

        _parameters = parameters or []
        if _parameters == []:
            raise ValueError("For some reason, no parameters are specified!")

        _contexts = contexts or []
        if _contexts == []:
            raise ValueError("For some reason, no contexts are specified!")

        key = [n["parameters"]["key"] for n in _contexts if n["name"] == "key"][0]
        digits_required = [n["parameters"]["digits"] for n in _contexts if n["name"] == "digits"][0]
        guesses = [n["parameters"]["guesses"] for n in _contexts if n["name"] == "guesses"][0]
        digits_guessed = [int(n) for n in _parameters.get("digitlist", None)]

        guess_analysis = helper.mkae_guess(key=key, digits_required=digits_required, digits=digits_guessed)
        game = guess_analysis.get('game', None)
        outcome = guess_analysis.get('outcome', None)
        status = game.get('status', None)
        message = outcome.get('message', None)

        logging.debug('Key: {}. Digits required: {}. Guesses: {}'.format(key, digits_required, guesses))
        logging.debug('Digits guessed are: {}'.format(digits_guessed))

        return {
            "contextOut": contexts,
            "speech": message,
            "displayText": message
        }

    def perform_newgame(self, cowbull_url=None, parameters=None):
        helper = WebhookHelpers(cowbull_url=cowbull_url)

        _parameters = parameters or {"mode": "normal"}
        _mode = _parameters.get('mode', None)
        if _mode is None:
            _mode = "normal"

        logging.debug("Validating game mode")
        if not helper.validate_mode(mode=_mode):
            raise ValueError("The mode {} is not supported".format(_mode))

        logging.debug("Starting a new game in {} mode". format(_mode))
        game_object = helper.fetch_new_game()

        text_return = "Okay, I've started a new game. You have {} guesses to guess {} numbers."\
            .format(game_object["guesses"],game_object["digits"])

        return_object = {
            "contextOut": [
                {"name": "digits", "lifespan": 15, "parameters": {"digits": game_object["digits"]}},
                {"name": "guesses", "lifespan": 15, "parameters": {"guesses": game_object["guesses"]}},
                {"name": "key", "lifespan": 15, "parameters": {"key": game_object["key"]}},
                {"name": "served-by", "lifespan": 15, "parameters": {"served-by": game_object["served-by"]}}
            ],
            "speech": text_return,
            "displayText": text_return
        }

        return return_object

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
        return Response(
            status=status_code,
            mimetype="application/json",
            response=json.dumps({
                "status": status_code,
                "message": response
            })
        )
