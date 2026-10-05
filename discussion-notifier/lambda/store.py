import hashlib
import os
import time

from botocore.exceptions import ClientError


class DeliveryBusy(RuntimeError):
    pass


class Store:
    def __init__(self, table=None):
        if table is None:
            import boto3

            table = boto3.resource("dynamodb").Table(os.environ["SETTINGS_TABLE"])
        self.table = table
        self.partition = (
            f"RULES#{os.environ['SLACK_TEAM_ID']}#{os.environ['GITHUB_REPOSITORY'].casefold()}"
        )

    def rules(self, kind=None, owner=None):
        items = []
        args = {
            "KeyConditionExpression": "pk = :pk",
            "ExpressionAttributeValues": {":pk": self.partition},
            "ConsistentRead": True,
        }
        while True:
            response = self.table.query(**args)
            items.extend(response["Items"])
            if not response.get("LastEvaluatedKey"):
                break
            args["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        if not any(item["sk"] == "BOOTSTRAP" for item in items):
            self.bootstrap()
            return self.rules(kind, owner)
        return [
            item
            for item in items
            if item["sk"] != "BOOTSTRAP"
            and (kind is None or item["kind"] == kind)
            and (owner is None or item["owner"] == owner)
        ]

    def bootstrap(self):
        from notifications import DEFAULT_EVENTS

        item = self.rule_item(
            "channel", os.environ["DEFAULT_CHANNEL_ID"], "all", "", DEFAULT_EVENTS
        )
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        self.table.put_item(Item={"pk": self.partition, "sk": "BOOTSTRAP"})

    def rule_item(self, kind, owner, scope, selector, events):
        digest = hashlib.sha256(selector.encode()).hexdigest()[:32]
        key = f"{kind}#{owner}#{scope}#{digest}"
        return {
            "pk": self.partition,
            "sk": key,
            "kind": kind,
            "owner": owner,
            "scope": scope,
            "selector": selector,
            "events": sorted(events),
        }

    def save(self, kind, owner, scope, selector, events):
        item = self.rule_item(kind, owner, scope, selector, events)
        self.table.put_item(Item=item)
        return item

    def remove(self, key):
        self.table.delete_item(Key={"pk": self.partition, "sk": key})

    def receipt_key(self, delivery, destination):
        return {"pk": f"DELIVERY#{delivery}", "sk": "#".join(destination)}

    def claim(self, delivery, destination):
        key = self.receipt_key(delivery, destination)
        now = int(time.time())
        try:
            self.table.put_item(
                Item={
                    **key,
                    "status": "sending",
                    "lease_until": now + 120,
                    "expires_at": now + 604800,
                },
                ConditionExpression="attribute_not_exists(pk) OR (#s = :sending AND lease_until < :now) OR expires_at < :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":sending": "sending", ":now": now},
            )
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            item = self.table.get_item(Key=key, ConsistentRead=True).get("Item", {})
            if item.get("status") == "sent":
                return False
            raise DeliveryBusy("destination-in-progress") from None

    def complete(self, delivery, destination):
        self.table.put_item(
            Item={
                **self.receipt_key(delivery, destination),
                "status": "sent",
                "expires_at": int(time.time()) + 604800,
            }
        )
