import json
import logging
import os

from decimal import Decimal
from typing import Any, Optional

import boto3

from botocore.paginate import Paginator
from botocore.client import BaseClient
from datetime import datetime, timedelta


logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)
print(os.getcwd())

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "alarm-evaluator")
DESCRIPTION_TABLE_NAME = os.environ.get(
    "DYNAMODB_DESCRIPTION_TABLE", "alarm-description"
)
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
AWS_BEDROCK_REGION = os.environ.get("AWS_BEDROCK_REGION", "us-west-2")

cw_client = boto3.client("cloudwatch", region_name=AWS_REGION)
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime", region_name=AWS_BEDROCK_REGION
)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
basic_alarm_table = dynamodb.Table(TABLE_NAME)
alarm_description_table = dynamodb.Table(DESCRIPTION_TABLE_NAME)


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
) -> dict:
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
    return {
        "no_description": alarms_without_description,
        "high_threshold": alarms_with_too_high_threshold,
        "high_data_points": alarms_with_too_high_data_points,
        "no_actions": alarms_without_actions,
    }


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


def check_alarm_history(alarm_history: dict) -> dict:
    """
    Checks the history of an alarm to determine if the alarm fails any criteria

    Args:
        alarm (dict): A CloudWatch alarm dict object

    Returns:
        dict: The full response from Amazon Bedrock
    """

    long_lived_alarm_count = 0
    long_term_issue_count = 0
    recurring_in_12_hours_count = 0
    short_alarm_count = 0

    for alarm in reversed(alarm_history):
        if alarm["HistoryItemType"] != "StateUpdate":
            logging.info("Non Status Update data")
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
                    (
                        f"Long Term Issue Alarm.\n"
                        f"Prev Close: {prev_alarm_close_time}\n"
                        f"New Trigger: {alarm_start_time}.\n"
                        f"Time Delta: {time_between_close_and_trigger}"
                    )
                )
            if time_between_close_and_trigger <= timedelta(hours=12):
                recurring_in_12_hours_count += 1
                print(
                    (
                        f"Recurring in 12 Hours Alarm.\n"
                        f"Prev Close: {prev_alarm_close_time}\n"
                        f"New Trigger: {alarm_start_time}.\n"
                        f"Time Delta: {time_between_close_and_trigger}"
                    )
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
                    (
                        f"Long Lived Alarm.\nTrigger: {alarm_start_time}\n"
                        f"Close: {alarm_close_time}.\n"
                        f"Time Delta: {time_between_close_and_trigger}"
                    )
                )
            elif time_to_solve <= timedelta(minutes=2):
                short_alarm_count += 1
                print(
                    (
                        f"Short Lived Alarm.\nTrigger: {alarm_start_time}\n"
                        f"Close: {alarm_close_time}.\n"
                        f"Time Delta: {time_between_close_and_trigger}"
                    )
                )

    return {
        "long_lived_alarm_count": long_lived_alarm_count,
        "long_term_issue_count": long_term_issue_count,
        "recurring_in_12_hours_count": recurring_in_12_hours_count,
        "short_alarm_count": short_alarm_count,
    }


def generate_message(bedrock_runtime, model_id, system_prompt, messages):
    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "system": system_prompt,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2000,
        }
    )

    response = bedrock_runtime.invoke_model(body=body, modelId=model_id)
    response_body = json.loads(response.get("body").read())

    return response_body


def verify_llm_response(
    llm_response: dict, prefill: Optional[str] = None
) -> dict:
    """
    Verifies the output of an LLM to determine if it is valid JSON

    Args:
        llm_output (str): The output of the LLM

    Returns:
        bool: True if the output is valid, False otherwise
    """

    llm_text = llm_response["content"][0]["text"]

    if prefill:
        llm_text = prefill + llm_text

    try:
        llm_json = json.loads(llm_text)
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing LLM output:\n{llm_json}\n{e}")
        return {}

    return llm_json


def check_alarm_description(
    alarm: dict, prefill: Optional[str] = None
) -> dict:
    """
    Checks the description of an alarm and suggests improvements
    Args:
        alarm (dict): A CloudWatch alarm dict object
        prefill (str, optional): String to prefill the LLM response with.
                                 Defaults to None.
    Returns:
        dict: The full response from Amazon Bedrock
    """

    bedrock_runtime = boto3.client(
        service_name="bedrock-runtime", region_name="us-west-2"
    )

    model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    # This model is better but we are rate limited internally
    # model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    # model_id = "anthropic.claude-3-5-haiku-20241022-v1:0"
    system_prompt = """
    You are a helpful assistant that analyzes CloudWatch Alarm data.
    You assess whether alarm descriptions are meaningful and representative of
    the alarm.
    You will be presented an Alarm description (in <desc>) tags
    and a JSON object that describes the alarm (in <alarm> tags).
    If the alarm description is not in the object, is None or is a blank
    string, suggest a new description
    Alarm descriptions should be descriptive, containing information on what
    metric triggers the alarm as well as the threshold and
    what actions are triggered.
    Additionally, it is good practice to link a playbook (only 1 link should
    be included).

    After assessing the alarm, provide a suggested new alarm
    description that incorporates your feedback.

    When returning your output, be succinct in your assessment,
    skip any preamble and wrap it into a JSON object like the following:
    {
        "assessment": <your assessment>,
        "suggested_description": <your suggested description>
    }
    """

    u_msg = (
        f"Evaluate if the description is meaningful and representative"
        f"of the alarm then sugggest a new alarm if necessary.\n\n"
        f"<desc>{alarm.get("AlarmDescription")}</desc>\n\n"
        f"<alarm>{json.dumps(alarm, default=str)}</alarm>\n\n"
    )

    user_message = {"role": "user", "content": u_msg}
    messages = [user_message]

    if prefill:
        prefill_msg = {"role": "assistant", "content": prefill}
        messages.append(prefill_msg)

    response = generate_message(
        bedrock_runtime, model_id, system_prompt, messages
    )
    logging.info(json.dumps(response, indent=2))

    return response


def convert_invalid_types(alarm: dict) -> dict:
    """
    Converts invalid types in a dict to valid Dynamo types

    Args:
        dict: A dict object of alarm details

    Returns:
        dict: The alarm dict with Dynamo compatible types
    """

    logging.info(f"Converting invalid types: {alarm.get("AlarmName")}")
    for k, v in alarm.items():
        logging.info(f"{k}:{v}")
        if isinstance(v, datetime):
            alarm[k] = v.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
        elif isinstance(v, float):
            alarm[k] = Decimal(str(v))

    return alarm


def write_basic_alarm_checks_to_dynamo(alarms_dict: dict) -> dict:
    """
    Writes the basic alarm checks to DynamoDB

    Args:
        alarms_dict (dict): A dictionary containing the basic alarm checks
    Returns:
        dict: Status code dictionary

    """

    logging.info(f"Writing basic alarm checks to {TABLE_NAME} in {AWS_REGION}")
    try:
        for key, value in alarms_dict.items():
            for alarm in value:
                alarm = convert_invalid_types(alarm)
            item = {"id": key, "alarm_list": value}
            basic_alarm_table.put_item(Item=item)

            logging.info(f"Successfully wrote {key} to DynamoDB table")
            logging.info(f"Item: {json.dumps(item, default=str)}")

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


def write_alarm_description_to_dynamo(alarm_map: dict):
    """
    Writes the alarm description suggestion and flags for
    alarm checks to DynamoDB

    Args:
        alarm_map (dict): A dictionary containing the alarms and check results
    Returns:
        dict: Status code dictionary

    """
    logging.info(
        f"Writing alarm descriptions to {DESCRIPTION_TABLE_NAME} in {AWS_REGION}"
    )
    try:
        for alarm_id, alarm_attributes in alarm_map.items():
            item = {"id": alarm_id}
            convert_invalid_types(alarm_attributes)
            for k, v in alarm_attributes.items():
                item[k] = v
            logging.info(f"\n\nItem: {json.dumps(item, default=str)}")
            alarm_description_table.put_item(Item=item)

            logging.info(f"Successfully wrote {alarm_id} to DynamoDB table")
            logging.info(f"Item: {json.dumps(item, default=str)}")

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


def create_alarm_map(alarms_list: list[dict]) -> dict:
    """
    Function that takes a list of CW Alarms and
    produces a dictionary of those alarms where the key is
    the alarm ARN and the value is the list of flags
    corresponding to checks carried out.

    Args:
        alarms_list (list[dict]): A list of CW Alarms
    Returns:
        dict: A dictionary of CW Alarms with Arn as the key

    """

    alarms_dict: dict = {}

    for alarm in alarms_list:
        alarms_dict[alarm["AlarmArn"]] = {
            "AlarmName": alarm.get("AlarmName"),
            "AlarmDescription": alarm.get("AlarmDescription"),
            "ActionsEnabled": alarm.get("ActionsEnabled"),
            "OKActions": alarm.get("OKActions"),
            "AlarmActions": alarm.get("AlarmActions"),
            "InsufficientDataActions": alarm.get("InsufficientDataActions"),
        }

    return alarms_dict


def create_alarm_with_flags(
    basic_alarm_checks_dict: dict, alarm_map: dict
) -> dict:
    """
    Function that takes the basic alarm checks dictionary and an alarm map
    and adds flags to the map to represent issues with each alarm

    Args:
        basic_alarm_checks_dict (dict): A dictionary of alarms and flags
        alarm_map (dict): A dictionary of alarms with Arn as the key
    Returns:
        dict: A dictionary of alarms with Arn as the key and added flag values

    """
    logging.info("Adding flags to alarms")

    for check_type, alarms_list in basic_alarm_checks_dict.items():
        if len(alarms_list) == 0:
            continue
        for alarm in alarms_list:
            arn = alarm["AlarmArn"]
            alarm_detail = alarm_map[arn]
            alarm_detail[check_type] = True
    return alarm_map


if __name__ == "__main__":
    metrics_alarm_list, composit_alarms_list = retrieve_all_cw_alarms(
        cw_client
    )

    alarm_map = create_alarm_map(metrics_alarm_list)

    basic_alarm_checks_dict = basic_alarm_checks(metrics_alarm_list)

    logging.info(
        f"""Number of Alarms Missing Descriptions:
        {len(basic_alarm_checks_dict['no_description'])}"""
    )
    logging.info(
        f"""Number of Alarms With High Thresholds:
        {len(basic_alarm_checks_dict['high_threshold'])}"""
    )
    logging.info(
        f"""Number of Alarms High Data Points:
        {len(basic_alarm_checks_dict['high_data_points'])}"""
    )
    logging.info(
        f"""Number of Alarms Without Actions:
        {len(basic_alarm_checks_dict['no_actions'])}"""
    )

    write_basic_alarm_checks_to_dynamo(basic_alarm_checks_dict)

    # Quotes need to be escaped here. Beware Ruff changes them.
    prefill = "{\"assessment\":"
    for alarm in metrics_alarm_list:
        alarm_description_check = check_alarm_description(alarm, prefill)
        llm_json_output = verify_llm_response(alarm_description_check, prefill)
        logging.info(f"LLM Output: {llm_json_output}")
        alarm_map[alarm["AlarmArn"]]["DescriptionAssessment"] = (
            llm_json_output.get("assessment")
        )
        alarm_map[alarm["AlarmArn"]]["SuggestedDescription"] = (
            llm_json_output.get("suggested_description")
        )
        logging.info(
            f"Alarm Map: {json.dumps(alarm_map[alarm["AlarmArn"]], indent=2)}"
        )
    dynamo_response = write_alarm_description_to_dynamo(alarm_map)
    logging.info(f"Dynamo Response: {dynamo_response}")
