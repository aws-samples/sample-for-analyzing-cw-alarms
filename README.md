# CloudWatch Alarm Analyser

This alarm analyser will examine all of your Amazon CloudWatch Alarms in a specific region and identify common alarm issues as well as providing Bedrock (GenAI) generated alarm descriptions for each of your alarms in order to make them more meaningful. Results are displayed in CloudWatch Dashboards custom widgets. Alarm issues are defined as follows:

| Issue | Description |
|:---|:---|
| Alarms with no description | Alarms should have a meaninful description and a link to playbook/runbook |
| Alarms with no actions | Alarms with no actions configured - unless they are a part of a composite alerts, why have an alarm if you intend to take no action? These are costly and likely provide no value |
| Long sounding alarms | Consider why these alarms sound for long periods of time and do not close. Are these genuinely long standing issues or just noisy alarms being ignored? |
| Alarm set for too many data points | Alarms requiring review of thresholds as they have a high number of data points to hit before they alert. |
| Alarms re-alerting within 12hrs | Alarms which alert at least twice in 12 hours, several times in a month or week and repeat. This may indicate that there is a long term fix is required. |
| Alarms that occur daily | Noisy alarms which imply that the issue is either not fixed long term or alarm is being ignored |
| Alarms closing within 2mins | Alarms which are alerting and then quickly closing themselves within a short space of time. |
| Alarm threshold set too high | The alarm threshold may be set too high and never sound. Please review to make sure alarm is effective. |


## Deployment
To deploy the alarm analyser, please follow these steps:
1. Navigate to Amazon Bedrock on the AWS Console and then to **Model Access**. Select **Enable specific models** or **Modify model access** and enable access to `Claude 3 Sonnet`. (please note that it has to be this model and not the later one)
1. Navigate to the Amazon S3 console and identify an Amazon S3 bucket of your choice in the account and region to which you wish to deploy the analyser or [create a new bucket](https://docs.aws.amazon.com/AmazonS3/latest/userguide/create-bucket-overview.html). [Upload](https://docs.aws.amazon.com/AmazonS3/latest/userguide/upload-objects.html) `.src/alarm_evaluator.py` to this bucket. Only copy the file and not the src folder.
1. In the same region, navigate to the CloudFormation console, deploy `template.yml` making sure you specify the parameters as follows:

    | Parameter | Default Value | Description |
    |:---|:---|:---|
    | `BedrockRegion` | us-west-1 | Specify the region in which you have enabled the model |
    | `EnvironmentName` | dev | Specify a name of your choice |
    | `S3BucketName` | N/A | Specify the bucket to which you copied the file |
    | `S3SourceFile` | `alarm_evaluator.py` | Leave the file name as default but add full path if you copied the file to a folder within a bucket |

1. Wait for deployment to complete.

1. Navigate to the AWS CodeBuild console and identify a job named `{EnvironmentName}-alarm-evaluator`. Select the job and click **Start Build**. Observe the job until it has completed making sure it has no errors.
1. Your alarm analyser is now ready and scheduled to run every Monday. Once the scheduled task completes, examine the `{EnvironmentName}-alarm-evaluator-dashboard` in The CloudWatch Dashboard console to view your report. Please make sure you select **Allow always** to allow the custom widget Lambdas to populate your dashbaord.
1. Optional - If you wish to run your analysis immediately instead of waiting for the scheduled task to run, navigate to the Amazon ECS console, locate the `{EnvironmentName}-alarm-evaluator-cluster`, head to **Tasks** and **Run new task**. Leave compute configuration as default (Launch type, Fargate, latest). Under **Deployment configuration** select **Task** and under **Family**, select `{EnvironmentName}-alarm-evaluator-task` then select the latest revision listed under **Revisions**. Make sure desired tasks is set to `1` and under **Networking** chose the new VPC which was created in the CloudFormation template. Leave the rest as default then click **Create**. Wait for the task to complete. Examine the `{EnvironmentName}-alarm-evaluator-dashboard` in The CloudWatch Dashboard console to view your report.
1. In your report, you can review the list of alarms with specific issues as well as the list of suggested descriptions. Each alarm is hyperlinked so that you can easily open the alarm in order to edit if you wish to do so.

## Cleanup
1. If you no longer require the analyser, delete the CloudFormation stack making sure that you 1st empty the ECR repositry named `{EnvironmentName}-alarm-evaluator-repo` by deleteing all images contained in the registry.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
