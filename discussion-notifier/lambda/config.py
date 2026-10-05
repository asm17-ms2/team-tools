import os
import time

_cache = {}


def secret(env_name):
    name = os.environ[env_name]
    cached = _cache.get(name)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]
    import boto3

    keys = [env_name]
    if env_name.startswith("SLACK_"):
        keys = ["SLACK_SIGNING_SECRET_PARAM", "SLACK_BOT_TOKEN_PARAM"]
    names = [os.environ[key] for key in keys]
    parameters = boto3.client("ssm").get_parameters(Names=names, WithDecryption=True)["Parameters"]
    for parameter in parameters:
        _cache[parameter["Name"]] = (time.monotonic(), parameter["Value"])
    return _cache[name][1]
