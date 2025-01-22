
#!/bin/bash

# Set namespace to current or default if not explicitly set
NAMESPACE=$(kubectl config view --minify --output 'jsonpath={..namespace}')
NAMESPACE=${NAMESPACE:-default}

echo "Rolling back Deployments in namespace: $NAMESPACE"

# Get all Deployments in the namespace
DEPLOYMENTS=$(kubectl get deployments -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}')

# Prompt user for rollback option
echo "Do you want to rollback to a specific revision or relative revision?"
echo "Enter 'specific' for a specific revision or 'relative' for +1 (next) or -1 (previous) rollback:"
read ROLLBACK_TYPE

if [ "$ROLLBACK_TYPE" == "specific" ]; then
  echo "Enter the revision number to rollback to:"
  read REVISION
elif [ "$ROLLBACK_TYPE" == "relative" ]; then
  echo "Enter +1 to rollback to the next revision or -1 to rollback to the previous revision:"
  read RELATIVE
else
  echo "Invalid option. Exiting."
  exit 1
fi

# Prompt user for a change cause
echo "Enter the change cause for this rollback operation (e.g., 'Rollback due to issue XYZ'):"
read CHANGE_CAUSE

# Initialize a summary report file
REPORT_FILE="rollback_summary_report.txt"
echo "Rollback Summary Report" > $REPORT_FILE
echo "Namespace: $NAMESPACE" >> $REPORT_FILE
echo "---------------------------------------" >> $REPORT_FILE

# Initialize counters for success and failure
SUCCESS_COUNT=0
FAILURE_COUNT=0
FAILED_DEPLOYMENTS=()

# Loop through each Deployment and perform the rollback
for DEPLOYMENT in $DEPLOYMENTS; do
  echo "Rolling back Deployment: $DEPLOYMENT"

  if [ "$ROLLBACK_TYPE" == "specific" ]; then
    # Rollback to the specified revision
    kubectl rollout undo deployment/$DEPLOYMENT --to-revision=$REVISION -n $NAMESPACE
  elif [ "$ROLLBACK_TYPE" == "relative" ]; then
    if [ "$RELATIVE" == "-1" ]; then
      # Rollback to the previous revision
      kubectl rollout undo deployment/$DEPLOYMENT -n $NAMESPACE
    else
      echo "Relative rollbacks other than -1 (previous) are not supported. Skipping $DEPLOYMENT."
      continue
    fi
  fi

  # Check the status of the rollback
  if kubectl rollout status deployment/$DEPLOYMENT -n $NAMESPACE; then
    # If successful, increment the success counter
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    echo "Rollback successful for Deployment: $DEPLOYMENT"
  else
    # If failed, increment the failure counter and log the failed deployment
    FAILURE_COUNT=$((FAILURE_COUNT + 1))
    FAILED_DEPLOYMENTS+=($DEPLOYMENT)
    echo "Rollback failed for Deployment: $DEPLOYMENT"
  fi

  # Annotate the deployment with the change cause
  kubectl annotate deployment/$DEPLOYMENT -n $NAMESPACE kubernetes.io/change-cause="$CHANGE_CAUSE" --overwrite

  # Get the new revision history
  echo "Deployment: $DEPLOYMENT" >> $REPORT_FILE
  kubectl rollout history deployment/$DEPLOYMENT -n $NAMESPACE >> $REPORT_FILE
  echo "---------------------------------------" >> $REPORT_FILE

done

# Summarize the results
echo "Rollback Summary:" >> $REPORT_FILE
echo "Total Successful Rollbacks: $SUCCESS_COUNT" >> $REPORT_FILE
echo "Total Failed Rollbacks: $FAILURE_COUNT" >> $REPORT_FILE

if [ $FAILURE_COUNT -gt 0 ]; then
  echo "Failed Deployments:" >> $REPORT_FILE
  for FAILED_DEPLOYMENT in "${FAILED_DEPLOYMENTS[@]}"; do
    echo "- $FAILED_DEPLOYMENT" >> $REPORT_FILE
  done
fi

# Display the rollback summary report
echo "Rollback process completed for all Deployments in namespace '$NAMESPACE'."
echo "The rollback summary report has been saved to $REPORT_FILE."
cat $REPORT_FILE
