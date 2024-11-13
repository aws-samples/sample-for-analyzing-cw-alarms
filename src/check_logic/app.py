import json
import logging
import os

from typing import Any, Optional

import boto3

from botocore.paginate import Paginator
from botocore.client import BaseClient
from datetime import datetime, timedelta, UTC


logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

# os.environ["AWS_PROFILE"] = "andevelt+docker-Admins"
# os.environ["AWS_REGION"] = "eu-west-1"

# cw_client = boto3.client("cloudwatch", region_name=os.environ["AWS_REGION"])

TABLE_NAME = os.environ.get("DYNAMODB_TABLE")
AWS_REGION = os.environ.get("AWS_REGION")

cw_client = boto3.client("cloudwatch", region_name=AWS_REGION)


def retrieve_all_cw_alarms(
    client: BaseClient,
) -> tuple[list[dict], list[dict]]:
    paginator: Paginator = client.get_paginator("describe_alarms")
    """
    Retrieve the full list of CloudWatch Alarms for the account and region

    Args:
        client (BaseClient): A Boto3 CloudWatch client

    Returns:
        tuple[list[dict], list[dict]]: A tuple containing two lists:
            - The first list contains all Metric Alarms
            - The second list contains all Composite Alarms
    """

    metric_alarms_list: list[dict] = []
    composite_alarms_list: list[dict] = []
    for page in paginator.paginate():
        logging.info(f"Page:\n {page}")
        for alarm in page["MetricAlarms"]:
            logging.info(f"Metric Alarm retrieved: {alarm}")
            metric_alarms_list.append(alarm)
        for alarm in page.get("CompositeAlarms", []):
            logging.info(f"Composite Alarm retrieved: {alarm}")
            composite_alarms_list.append(alarm)

    logging.info(f"Total Metric Alarms: {len(metric_alarms_list)}")
    logging.info(f"Total Composite Alarms: {len(composite_alarms_list)}")

    return metric_alarms_list, composite_alarms_list


def alarm_has_description(alarm: dict[str, Any]) -> bool:
    """
    Checks if an alarm contains a non-empty decsription

    Args:
        alarm (dict[str, Any]): A CloudWatch alarm dict object

    Returns:
        bool: True if the alarm has a non-empty description, False otherwise
    """
    alarm_desc: Optional[str] = alarm.get("AlarmDescription")
    if alarm_desc is None or alarm_desc.strip() == "":
        return False

    return True


def alarm_has_actions(alarm: dict[str, Any]) -> bool:
    """
    Checks if an alarm triggers any actions

    Args:
        alarm (dict[str, Any]): A CloudWatch alarm dict object

    Returns:
        bool: True if the alarm triggers actions, False otherwise
    """
    return True if len(alarm["AlarmActions"]) > 0 else False


def alarm_theshold_too_high(alarm: dict[str, Any]) -> bool:
    """
    Checks if the threshold for an alarm is too high (>30.0)

    Args:
        alarm (dict[str, Any]): A CloudWatch alarm dict object

    Returns:
        bool: True if the threshold is above 30.0, False otherwise
    """
    alarm_threshold: Optional[float] = alarm.get("Threshold")

    if not alarm_threshold or alarm_threshold > 30.0:
        return True
    return False


def alarm_data_points_too_high(alarm: dict[str, Any]) -> bool:
    """
    Checks if the number of data points for an alarm is too high (>15)

    Args:
        alarm (dict[str, Any]): A CloudWatch alarm dict object

    Returns:
        bool: True if the number of data points is above 15, False otherwise
    """
    alarm_data_points: Optional[int] = alarm.get("DatapointsToAlarm")

    if not alarm_data_points or alarm_data_points > 15:
        return True
    return False


def basic_alarm_checks(
    alarm_list: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Performs basic checks on a list of CloudWatch alarms

    Args:
        alarm_list (list[dict]): A list of CloudWatch alarm dict objects

    Returns:
        tuple[list[dict], list[dict], list[dict], list[dict]]: A tuple
        containing four lists of alarm dictionaries:
            1. Alarms without description
            2. Alarms with too high threshold
            3. Alarms with too high data points
            4. Alarms without actions
    """

    alarms_without_description: list[dict] = []
    alarms_with_too_high_threshold: list[dict] = []
    alarms_with_too_high_data_points: list[dict] = []
    alarms_without_actions: list[dict] = []

    for alarm in alarm_list:
        if not alarm_has_description(alarm):
            alarms_without_description.append(alarm)
        if alarm_theshold_too_high(alarm):
            alarms_with_too_high_threshold.append(alarm)
        if alarm_data_points_too_high(alarm):
            alarms_with_too_high_data_points.append(alarm)
        if not alarm_has_actions(alarm):
            alarms_without_actions.append(alarm)
    return (
        alarms_without_description,
        alarms_with_too_high_threshold,
        alarms_with_too_high_data_points,
        alarms_without_actions,
    )  # TODO: decide if it is better to wrap these into a single dict


def get_alarm_history(client: BaseClient, alarm: dict) -> list[dict]:
    """
    Gets the history of an alarm

    Args:
        client (BaseClient): A Boto3 CloudWatch client

    Returns:
        tuple[list[dict], list[dict]]: A tuple containing two lists:
            - The first list contains all Metric Alarms
            - The second list contains all Composite Alarms
    """
    response = cw_client.describe_alarm_history(AlarmName=alarm["AlarmName"])
    return response["AlarmHistoryItems"]


def get_alarm_start_time(
    alarm: dict, state_type: str = "newState"
) -> datetime:
    """
    Takes an alarm history item and returns the Start time for either the old
    or new state

    Args:
        alarm (dict[str, Any]): A CloudWatch alarm dict object
        state_type (str, optional): The state type to retrieve. Allowed values
                                    are newState or oldState.
                                    Defaults to "newState".

    Returns:
        datetime: The start time of the state
    """
    if state_type not in ["newState", "oldState"]:
        raise ValueError("state_type must be either 'newState' or 'oldState'")

    alarm_hist = json.loads(alarm["HistoryData"])
    alarm_start_time_string = alarm_hist[state_type]["stateReasonData"][
        "startDate"
    ]
    last_alarm_start_time = datetime.strptime(
        alarm_start_time_string, "%Y-%m-%dT%H:%M:%S.%f%z"
    )

    return last_alarm_start_time


def check_alarm_history(alarm_history: dict) -> bool:
    """
    Checks the history of an alarm to determine if the alarm fails any criteria

    Args:
        alarm (dict): A CloudWatch alarm dict object

    Returns:
        TODO: Fill out return value
    """

    long_lived_alarm_count = 0
    long_term_issue_count = 0
    recurring_in_12_hours_count = 0
    short_alarm_count = 0

    for alarm in reversed(alarm_history):
        if alarm["HistoryItemType"] != "StateUpdate":
            print("Non Status Update data")
            continue

        if alarm["HistorySummary"] == "Alarm updated from OK to ALARM":
            alarm_start_time = get_alarm_start_time(
                alarm, state_type="newState"
            )
            prev_alarm_close_time = get_alarm_start_time(
                alarm, state_type="oldState"
            )
            time_between_close_and_trigger = (
                alarm_start_time - prev_alarm_close_time
            )
            if time_between_close_and_trigger <= timedelta(hours=24):
                long_term_issue_count += 1
                print(
                    f"Long Term Issue Alarm.\nPrev Close: {prev_alarm_close_time}\nNew Trigger: {alarm_start_time}.\nTime Delta: {time_between_close_and_trigger}"
                )
            if time_between_close_and_trigger <= timedelta(hours=12):
                recurring_in_12_hours_count += 1
                print(
                    f"Recurring in 12 Hours Alarm.\nPrev Close: {prev_alarm_close_time}\nNew Trigger: {alarm_start_time}.\nTime Delta: {time_between_close_and_trigger}"
                )

        elif alarm["HistorySummary"] == "Alarm updated from ALARM to OK":
            alarm_close_time = get_alarm_start_time(
                alarm, state_type="newState"
            )
            alarm_start_time = get_alarm_start_time(
                alarm, state_type="oldState"
            )
            time_to_solve = alarm_close_time - alarm_start_time
            if time_to_solve >= timedelta(hours=48):
                long_lived_alarm_count += 1
                print(
                    f"Long Lived Alarm.\nPrev Close: {prev_alarm_close_time}\nNew Trigger: {alarm_start_time}.\nTime Delta: {time_between_close_and_trigger}"
                )
            elif time_to_solve <= timedelta(minutes=2):
                short_alarm_count += 1
                print(
                    f"Short Term Alarm.\nPrev Close: {prev_alarm_close_time}\nNew Trigger: {alarm_start_time}.\nTime Delta: {time_between_close_and_trigger}"
                )

    return {
        "long_lived_alarm_count": long_lived_alarm_count,
        "long_term_issue_count": long_term_issue_count,
        "recurring_in_12_hours_count": recurring_in_12_hours_count,
        "short_alarm_count": short_alarm_count,
    }


# remove this, it is just so i can test env variable for table name
def write_timestamp_to_dynamodb():
    try:
        # Create DynamoDB resource
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = dynamodb.Table(TABLE_NAME)

        # Get current timestamp
        current_time = datetime.now(UTC)
        timestamp = int(current_time.timestamp())

        # Create item to insert
        item = {
            "id": str(timestamp),
            "timestamp": timestamp,
            "datetime_utc": current_time.isoformat(),
            "date": current_time.date().isoformat(),
            "time": current_time.time().isoformat(),
        }

        # Write to DynamoDB
        response = table.put_item(Item=item)

        logger.info(
            f"Successfully wrote timestamp to DynamoDB table {TABLE_NAME}"
        )
        logger.info(f"Item: {json.dumps(item, default=str)}")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Successfully wrote timestamp to DynamoDB",
                    "item": item,
                },
                default=str,
            ),
        }

    except Exception as e:
        error_msg = f"Error writing to DynamoDB: {str(e)}"
        logger.error(error_msg)
        return {"statusCode": 500, "body": json.dumps({"error": error_msg})}


if __name__ == "__main__":
    # cw_client = boto3.client(
    #     "cloudwatch", region_name=os.environ["AWS_REGION"]
    # )
    # logging.info(os.environ["AWS_PROFILE"])
    # logging.info(os.environ["AWS_REGION"])

    cw_client = boto3.client("cloudwatch", region_name=AWS_REGION)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", 20), format="%(message)s")

    metrics_alarm_list, composit_alarms_list = retrieve_all_cw_alarms(
        cw_client
    )

    (write_timestamp_to_dynamodb())

    (
        metrics_alarms_without_description,
        metrics_alarms_with_too_high_threshold,
        metrics_alarms_with_too_high_data_points,
        metrics_alarms_without_actions,
    ) = basic_alarm_checks(metrics_alarm_list)

    logging.info(
        f"""Number of Alarms Missing Descriptions:
        {len(metrics_alarms_without_description)}"""
    )
    logging.info(
        f"""Number of Alarms With High Thresholds:
        {len(metrics_alarms_with_too_high_threshold)}"""
    )
    logging.info(
        f"""Number of Alarms High Data Points:
        {len(metrics_alarms_with_too_high_data_points)}"""
    )
    logging.info(
        f"""Number of Alarms Without Actions:
        {len(metrics_alarms_without_actions)}"""
    )
