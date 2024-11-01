import logging
import os

from typing import Any, Dict, List, Optional, Tuple

import boto3

from botocore.paginate import Paginator
from botocore.client import BaseClient

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

os.environ["AWS_PROFILE"] = "andevelt+docker-Admins"
os.environ["AWS_REGION"] = "eu-west-1"

cw_client = boto3.client("cloudwatch", region_name=os.environ["AWS_REGION"])


def retrieve_all_cw_alarms(
    client: BaseClient,
) -> Tuple[List[dict], List[dict]]:
    paginator: Paginator = client.get_paginator("describe_alarms")
    """
    Retrieve the full list of CloudWatch Alarms for the account and region

    Args:
        client (BaseClient): A Boto3 CloudWatch client

    Returns:
        Tuple[List[dict], List[dict]]: A tuple containing two lists:
            - The first list contains all Metric Alarms
            - The second list contains all Composite Alarms
    """

    metric_alarms_list: List[dict] = []
    composite_alarms_list: List[dict] = []
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


def alarm_has_description(alarm: Dict[str, Any]) -> bool:
    """
    Checks if an alarm contains a non-empty decsription

    Args:
        alarm (Dict[str, Any]): A CloudWatch alarm dict object

    Returns:
        bool: True if the alarm has a non-empty description, False otherwise
    """
    alarm_desc: Optional[str] = alarm.get("AlarmDescription")
    if alarm_desc is None or alarm_desc.strip() == "":
        return False

    return True


def alarm_has_actions(alarm: Dict[str, Any]) -> bool:
    """
    Checks if an alarm triggers any actions

    Args:
        alarm (Dict[str, Any]): A CloudWatch alarm dict object

    Returns:
        bool: True if the alarm triggers actions, False otherwise
    """
    return True if len(alarm["AlarmActions"]) > 0 else False


def alarm_theshold_too_high(alarm: Dict[str, Any]) -> bool:
    """
    Checks if the threshold for an alarm is too high (>30.0)

    Args:
        alarm (Dict[str, Any]): A CloudWatch alarm dict object

    Returns:
        bool: True if the threshold is above 30.0, False otherwise
    """
    alarm_threshold: Optional[float] = alarm.get("Threshold")

    if not alarm_threshold or alarm_threshold > 30.0:
        return True
    return False


def alarm_data_points_too_high(alarm: Dict[str, Any]) -> bool:
    """
    Checks if the number of data points for an alarm is too high (>15)

    Args:
        alarm (Dict[str, Any]): A CloudWatch alarm dict object

    Returns:
        bool: True if the number of data points is above 15, False otherwise
    """
    alarm_data_points: Optional[int] = alarm.get("DatapointsToAlarm")

    if not alarm_data_points or alarm_data_points > 15:
        return True
    return False


def basic_alarm_checks(
    alarm_list: List[dict],
) -> Tuple[List[dict], List[dict], List[dict], List[dict]]:
    """
    Performs basic checks on a list of CloudWatch alarms

    Args:
        alarm_list (List[dict]): A list of CloudWatch alarm dict objects

    Returns:
        Tuple[List[dict], List[dict], List[dict], List[dict]]: A tuple
        containing four lists of alarm dictionaries:
            1. Alarms without description
            2. Alarms with too high threshold
            3. Alarms with too high data points
            4. Alarms without actions
    """

    alarms_without_description: List[dict] = []
    alarms_with_too_high_threshold: List[dict] = []
    alarms_with_too_high_data_points: List[dict] = []
    alarms_without_actions: List[dict] = []

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


if __name__ == "__main__":
    cw_client = boto3.client(
        "cloudwatch", region_name=os.environ["AWS_REGION"]
    )
    logging.info(os.environ["AWS_PROFILE"])
    logging.info(os.environ["AWS_REGION"])

    metrics_alarm_list, composit_alarms_list = retrieve_all_cw_alarms(
        cw_client
    )
