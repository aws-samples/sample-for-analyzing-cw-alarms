# hmb-594-cw-alarm-analyser

This alarm analyzer will examine all of your Amazon CloudWatch Alarms in a specific region and identify "noisy" alarms as well as providing Bedrock (GenAi) generated alarm descriptions for each of your alarms in order to make them more meaninful.  Noisy alarms are defined as follows

Alarms with no description | Alarms should have a meaninful description and a link to playbook/runbook
Alarms with no actions | Alarms with no actions configure - unless they are a part of a composite alerts, why have an alarm if you intend to take no action?  These are costly and likely pointless
Long sounding alarms | Consider why these alarms sound for long periods of time and do not close.  Are these genuinely long standing issues or just noisy alarms being ignored?
Alarm set for too many data points | Alarms requiring review of thresholds as they have a high number of data points to hit before they alert.
Alarms re-alerting within 12hrs | Alarms which alert several times in a month or week and repeat.  This may indicate that there is a long term fix is required.
Alarms that occur daily | Noisy alarms which imply that the issue is either not fixed long term or alarm is being ignored
Alarms closing within 2mins | Alarms which are alerting and then quickly closing themselves within a short space of time.
Alarm threshold set too high | The alarm treshold may be set too high and never sound.  Please review to make sure alarm is effective.

To deploy the alarm analyzer, please follow these steps:
1. In Bedrock - request model access to XXXXX (Colin pls add)
2. Identify an Amazon S3 bucket of your choice in the account and region to which you wish to deply the analyzer.  Copy .src/alarm_evaluator.py to this bucket.  Only copy the file and not the src folder.
3. In the same region, navigate to the CloudFormation console, deploy template.yml making sure you specify the parameters as follows: Bedrock region - specify the region in which you have enabled the model e.g. us-west-1, EnvironmentName - specifify a name of your choice e.g. dev, S3BucketName - specify the bucket to which you copied the file e.g. analyzer-bucket-1, S3SourceFile - leave the file name as default "alarm_evaluator.py" but add full path if you copied the file to a folder within a bucket. Wait for deployment to complete.
4. Navigate to the AWS CodeBuild console and identify a job named {environment}-alarm-evaluator.  Select the job and click "Start Build".  Observe the job until it has completed making sure it has no errors.
5.  Your alarm analyzer is now ready and scheduled to run every Monday.  Once the scheduled task completes, examine the {environment}-alarm-evaluator-dashboard in The CloudWatch Dashboard console to view your report.  Please make sure you select "Allow always" to allow the custom widget Lambdas to populate your dashbaord.
6. Optional - If you wish to test, head to the Amazon ECS console, locate the {environemnt}-alarm-evaluator-cluster, head to "Tasks" and "Run new task".  Leave compute configuration as defeault (Launch type, Fargate, latest).  Under "Deployment configuration" select  "Task" and under Family, select {environment}-alarm-evaluator-task then select the latest revision listed under revisions.  Make sure desired tasks is set to 1 and leave the rest as default then xlick "Create".  Wait for the task to complete.  Examine the {environment}-alarm-evaluator-dashboard in The CloudWatch Dashboard console to view your report.
7.  In your report, you can review the list of alarms with specific issues as well as the list of suggested descriptions.  Each alarm is hyperlinked so that you can easily open the alarm in order to edit the descripton if you wish to do so.



Cleanup:
1. If you no longer require the analyzer, delete the CloudFormation stack making sure that you 1st empty the ECR repositry named "{environment}-alarm-evaluator-repo" by deleteing all images contained in the registry.