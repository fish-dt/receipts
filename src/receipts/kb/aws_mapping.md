# AWS Service Mapping Guide (synthetic guidance, check current AWS docs)
## SM-1 Schedules
Time-based triggers map to an EventBridge schedule. Specify the time zone explicitly.
## SM-2 Short single-purpose steps
Steps that finish quickly map to a Lambda function. Long or heavy steps map to a container task.
## SM-3 Multi-step chains
Ordered steps with retries and branching map to a Step Functions state machine.
## SM-4 Failure handling
Failures should be visible: send failed runs to a dead-letter queue or an alarm, never swallow them.
## SM-5 Least privilege
Each function gets its own role listing only the actions it uses.
