import configparser
import time

import requests
from cryptography.fernet import Fernet
from flask import Flask, request, jsonify, redirect
from flask_restful import Resource, Api
from flask_cors import CORS
from pymongo import MongoClient

config = configparser.ConfigParser()
config.read("config.ini")

app = Flask(__name__)
app.config["MONGO_URI"] = config["Mongo"]["mongo"]

client = MongoClient(config["Mongo"]["mongo"])
db = client.modboty

CORS(app)
api = Api(app)

fernet = Fernet(config["Mongo"]["key"].encode())

# 1 - success
# 2 - invalid code
# 3 - auth error
# 4 - wrong permissions
# 5 - bot is not connected to the channel


@app.route("/api/v1/auth")
def index():
    code = request.args.get("code")
    scope = request.args.get("scope")

    result_code = 1 if code else 2

    token_data = requests.post(
        f'https://id.twitch.tv/oauth2/token?client_id={config["Twitch"]["client_id"]}&client_secret={config["Twitch"]["client_secret"]}&code={code}&grant_type=authorization_code&redirect_uri=http://localhost:5000/api/v1/auth'
    ).json()

    if "access_token" not in token_data:
        result_code = 3
    elif set(scope.split()) != {
        "channel:manage:broadcast",
        "channel:manage:polls",
        "channel:manage:predictions",
        "channel:manage:vips",
        "channel:read:polls",
        "channel:read:predictions",
        "channel:read:subscriptions",
        "channel:read:vips",
        "moderation:read",
    }:
        result_code = 4

    if result_code == 1:
        user_data = requests.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Authorization": f'Bearer {token_data["access_token"]}',
                "Client-Id": config["Twitch"]["client_id"],
            },
        ).json()

        to_send = {
            "login": user_data["data"][0]["login"],
            "access_token": fernet.encrypt(
                token_data["access_token"].encode()
            ).decode(),
            "refresh_token": fernet.encrypt(
                token_data["refresh_token"].encode()
            ).decode(),
            "expire_time": time.time() + token_data["expires_in"],
        }
        data = db.config.find_one({"_id": 1})

        if user_data["data"][0]["login"] not in [
            channel["login"] for channel in data["channels"]
        ]:
            result_code = 5

        if result_code == 1 and [
            user
            for user in data.get("user_tokens", [{}])
            if user.get("login", "") == user_data["data"][0]["login"]
        ]:
            db.config.update_one(
                {"_id": 1, "user_tokens.login": user_data["data"][0]["login"]},
                {"$set": {"user_tokens.$": to_send}},
            )
        elif result_code == 1:
            db.config.update_one({"_id": 1}, {"$addToSet": {"user_tokens": to_send}})

    return redirect(f"http://localhost:8080/#/auth?result={result_code}")


if __name__ == "__main__":
    app.run(debug=False)
