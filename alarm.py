import json
import os
import uuid

from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError


def list_alarms_and_store_in_dynamodb():
    cloudwatch = boto3.client(
        "cloudwatch", region_name=os.environ["AWS_REGION"]
    )
    dynamodb = boto3.resource("dynamodb", region_name=os.environ["AWS_REGION"])
    table_name = "CloudWatchAlarms"

    table = create_or_get_table(dynamodb, table_name)

    paginator = cloudwatch.get_paginator("describe_alarms")

    for page in paginator.paginate():
        print(f"Page:\n {page}")
        for alarm in page["MetricAlarms"]:
            # print(f"Metric Alarm retrieved: {alarm}")
            store_alarm_and_analyze_history(cloudwatch, table, alarm)
        for alarm in page.get("CompositeAlarms", []):
            # print(f"Composite Alarm retrieved: {alarm}")
            store_alarm_and_analyze_history(cloudwatch, table, alarm)

    print(
        f"Alarm data, history, and analysis have been stored in the '{table_name}' DynamoDB table."
    )


def create_or_get_table(dynamodb, table_name):
    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "AlarmArn", "KeyType": "HASH"},
                {"AttributeName": "Timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "AlarmArn", "AttributeType": "S"},
                {"AttributeName": "Timestamp", "AttributeType": "S"},
            ],
            ProvisionedThroughput={
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5,
            },
        )
        table.wait_until_exists()
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            table = dynamodb.Table(table_name)
        else:
            raise
    return table


def store_alarm_and_analyze_history(cloudwatch, table, alarm):
    alarm_item = {
        "AlarmArn": alarm["AlarmArn"],
        "Timestamp": str(uuid.uuid4()),
        "AlarmName": alarm["AlarmName"],
        "AlarmDescription": alarm.get("AlarmDescription", "N/A"),
        "StateValue": alarm["StateValue"],
        "Type": "AlarmDetails",
    }
    table.put_item(Item=alarm_item)

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=14)

    history_items = []
    paginator = cloudwatch.get_paginator("describe_alarm_history")
    for page in paginator.paginate(
        AlarmName=alarm["AlarmName"],
        HistoryItemType="StateUpdate",
        StartDate=start_time,
        EndDate=end_time,
    ):
        print(page)
        history_items.extend(page["AlarmHistoryItems"])
    print(len(history_items))

    with open("alarms.jsonl", "w") as f:
        print("Alarms to store:")
        for item in history_items:
            history_item_to_store = {
                "AlarmArn": alarm["AlarmArn"],
                "Timestamp": item["Timestamp"].isoformat(),
                "HistoryItemType": item["HistoryItemType"],
                "HistorySummary": item["HistorySummary"],
                "HistoryData": item["HistoryData"],
                "Type": "AlarmHistory",
            }
            # table.put_item(Item=history_item_to_store)
            print(history_item_to_store)
            f.write(json.dumps(history_item_to_store))
            f.write("\n")

    # quick_alerts = analyze_quick_alerts(history_items)

    # analysis_item = {
    #     "AlarmArn": alarm["AlarmArn"],
    #     "Timestamp": datetime.utcnow().isoformat(),
    #     "Type": "AlarmAnalysis",
    #     "QuickAlerts": quick_alerts,
    # }
    # table.put_item(Item=analysis_item)


def analyze_quick_alerts(history_items):
    quick_alerts = []
    sorted_items = sorted(history_items, key=lambda x: x["Timestamp"])

    for i in range(len(sorted_items) - 1):
        current_item = sorted_items[i]
        next_item = sorted_items[i + 1]

        current_state = json.loads(current_item["HistoryData"])["newState"][
            "stateValue"
        ]
        next_state = json.loads(next_item["HistoryData"])["newState"][
            "stateValue"
        ]

        if current_state == "ALARM" and next_state == "OK":
            time_diff = next_item["Timestamp"] - current_item["Timestamp"]
            if time_diff <= timedelta(minutes=2):
                quick_alerts.append(
                    {
                        "AlertStart": current_item["Timestamp"].isoformat(),
                        "AlertEnd": next_item["Timestamp"].isoformat(),
                        "Duration": str(time_diff),
                    }
                )

    return quick_alerts


if __name__ == "__main__":
    print(os.environ["AWS_PROFILE"])
    os.environ["AWS_REGION"] = "eu-west-1"
    print(os.environ["AWS_REGION"])
    list_alarms_and_store_in_dynamodb()
