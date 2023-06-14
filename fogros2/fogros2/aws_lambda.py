
import abc
import json
import os
import subprocess
import random

from .cloud_instance import CloudInstance
from .name_generator import get_unique_name
from .util import (
    MissingEnvironmentVariableException,
    instance_dir,
    make_zip_file,
)

docker_file_template = '''
# Define function directory
ARG FUNCTION_DIR="/function"
ARG BASE_IMAGE="osrf/ros:humble-desktop"
FROM ${BASE_IMAGE} as build-image

# Install aws-lambda-cpp build dependencies
RUN apt-get update && \
  apt-get install -y \
  g++ \
  make \
  cmake \
  unzip \
  python3-pip \
  libcurl4-openssl-dev

# Include global arg in this stage of the build
ARG FUNCTION_DIR
# Create function directory
RUN mkdir -p ${FUNCTION_DIR}

# Copy function code
COPY ./src/FogROS2-lambda/fogros2/app/* ${FUNCTION_DIR}

# Install the runtime interface client
RUN pip install \
        --target ${FUNCTION_DIR} \
        awslambdaric

# Multi-stage build: grab a fresh copy of the base image
FROM ${BASE_IMAGE}

# Include global arg in this stage of the build
ARG FUNCTION_DIR
# Set working directory to function root directory
WORKDIR ${FUNCTION_DIR}

# Copy in the build image dependencies
COPY --from=build-image ${FUNCTION_DIR} ${FUNCTION_DIR}


WORKDIR fog_ws
RUN mkdir install
COPY ./install ./install

ENTRYPOINT [ "/usr/bin/python3", "-m", "awslambdaric" ]
CMD [ "app.handler" ]
'''
class AWSLambdas(CloudInstance):
    """AWS Implementation of CloudInstance."""
    def __init__(self, 
        ros_workspace=os.path.dirname(os.getenv("COLCON_PREFIX_PATH")),
        working_dir_base=instance_dir(),
    ):
        self.ros_workspace = ros_workspace
        self._name = get_unique_name()
        self._working_dir_base = working_dir_base
        self._working_dir = os.path.join(self._working_dir_base, self._name)
        os.makedirs(self._working_dir, exist_ok=True)

        self.version = str(random.randint(0, 999))
        self.docker_repo_uri = "736982044827.dkr.ecr.us-west-1.amazonaws.com/fogros_lambda"
        self.lambda_name = f"fogros-lambda-{self.version}"
        self.image_name = f"{self.docker_repo_uri}:{self.version}"
        self.response_file_name = f"/tmp/response-{self.lambda_name}.json"




    def create(self):
        self.create_docker_file()
        subprocess.call(f"cd {self.ros_workspace} && docker build -t fogros-lambda-image . ", shell=True)
        subprocess.call(f"docker tag fogros-lambda-image:latest {self.image_name}", shell=True)
        subprocess.call(f"docker push {self.image_name}", shell=True)
        subprocess.call(f"aws lambda create-function --function-name {self.lambda_name}  --package-type Image   --code ImageUri={self.image_name}  --output text --role arn:aws:iam::736982044827:role/RoleLambda", shell=True)
        from time import sleep
        sleep(60)
        subprocess.call(f"aws lambda invoke --function-name {self.lambda_name} {self.response_file_name}", shell=True)

        



    def create_docker_file(self): 
        with open(self.ros_workspace + "/Dockerfile", "w+") as f:
            f.write(docker_file_template)
