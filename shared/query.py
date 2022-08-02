import urllib
import os
import json


def query_aws(account, query, region=None):
    if not region:
        file_name = f"account-data/{account.name}/{query}.json"
    else:
        if not isinstance(region, str):
            region = region.name
        file_name = f"account-data/{account.name}/{region}/{query}.json"
    return json.load(open(file_name)) if os.path.isfile(file_name) else {}


def get_parameter_file(region, service, function, parameter_value):
    file_name = f"account-data/{region.account.name}/{region.name}/{service}-{function}/{urllib.parse.quote_plus(parameter_value)}"

    if not os.path.isfile(file_name):
        return None
    return None if os.path.getsize(file_name) <= 4 else json.load(open(file_name))
