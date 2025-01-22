#!/bin/bash

DEPLOYMENT_NAME="rasa-cti-app"
NAMESPACE="giccdevbot"

# Get the active ReplicaSet
ACTIVE_RS=$(kubectl get replicasets -n $NAMESPACE -l app=$DEPLOYMENT_NAME -o jsonpath="{.items[?(@.status.replicas>0)].metadata.name}")

if [ -z "$ACTIVE_RS" ]; then
  echo "No active ReplicaSet found for deployment $DEPLOYMENT_NAME."
  exit 1
fi

# Get the active revision
ACTIVE_REVISION=$(kubectl get replicasets/$ACTIVE_RS -n $NAMESPACE -o jsonpath="{.metadata.annotations['deployment.kubernetes.io/revision']}")

# Get the image version
IMAGE_VERSION=$(kubectl get replicasets/$ACTIVE_RS -n $NAMESPACE -o jsonpath="{.spec.template.spec.containers[*].image}")

echo "Active ReplicaSet: $ACTIVE_RS"
echo "Active Revision: $ACTIVE_REVISION"
echo "Image Version: $IMAGE_VERSION"
