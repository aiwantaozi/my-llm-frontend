terraform {
  required_providers {
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = "1.14.0"
    }
  }
}

resource "kubectl_manifest" "amazon-light-gpt" {
  yaml_body = <<YAML
apiVersion: ray.io/v1alpha1
kind: RayService
metadata:
  name: amazon-light-gpt
spec:
  serviceUnhealthySecondThreshold: 1200 # Config for the health check threshold for service. Default value is 60.
  deploymentUnhealthySecondThreshold: 1200 # Config for the health check threshold for deployments. Default value is 60.
  serveConfigV2: |
    applications:
    - name: amazon--LightGPT
      import_path: aviary.backend:llm_application
      route_prefix: /amazon--LightGPT
      args:
        model: "./models/continuous_batching/amazon--LightGPT.yaml"
    - name: router
      import_path: aviary.backend:router_application
      route_prefix: /
      args:
        models:
          amazon/LightGPT: ./models/continuous_batching/amazon--LightGPT.yaml
  rayClusterConfig:
    # Ray head pod template
    headGroupSpec:
      # The `rayStartParams` are used to configure the `ray start` command.
      # See https://github.com/ray-project/kuberay/blob/master/docs/guidance/rayStartParams.md for the default settings of `rayStartParams` in KubeRay.
      # See https://docs.ray.io/en/latest/cluster/cli.html#ray-start for all available options in `rayStartParams`.
      rayStartParams:
        resources: '"{\"accelerator_type_cpu\": 2}"'
        dashboard-host: "0.0.0.0"
      #pod template
      template:
        spec:
          containers:
            - name: ray-head
              image: anyscale/aviary:latest
              resources:
                limits:
                  cpu: 2
                  memory: 8Gi
                requests:
                  cpu: 2
                  memory: 8Gi
              ports:
                - containerPort: 6379
                  name: gcs-server
                - containerPort: 8265 # Ray dashboard
                  name: dashboard
                - containerPort: 10001
                  name: client
                - containerPort: 8000
                  name: serve
    workerGroupSpecs:
      # the pod replicas in this group typed worker
      - replicas: 1
        minReplicas: 0
        maxReplicas: 1
        # logical group name, for this called small-group, also can be functional
        groupName: gpu-group
        rayStartParams:
          resources: '"{\"accelerator_type_cpu\": 48, \"accelerator_type_a10\": 2, \"accelerator_type_a100\": 2}"'
        #pod template
        template:
          spec:
            containers:
              - name: llm
                image: anyscale/aviary:latest
                lifecycle:
                  preStop:
                    exec:
                      command: ["/bin/sh", "-c", "ray stop"]
                resources:
                  limits:
                    cpu: "48"
                    memory: "192G"
                    nvidia.com/gpu: 4
                  requests:
                    cpu: "36"
                    memory: "128G"
                    nvidia.com/gpu: 4
                ports:
                  - containerPort: 8000
                    name: serve
            # Please add the following taints to the GPU node.
            tolerations:
              - key: "ray.io/node-type"
                operator: "Equal"
                value: "worker"
                effect: "NoSchedule"
YAML
}

resource "kubectl_manifest" "serve-amazon-light-gpt" {
  yaml_body = <<YAML
# Make sure to increase resource requests and limits before using this example in production.
# For examples with more realistic resource configuration, see
# ray-cluster.complete.large.yaml and
# ray-cluster.autoscaler.large.yaml.
apiVersion: ray.io/v1alpha1
kind: RayService
metadata:
  name: serve-amazon-light-gpt
spec:
  serviceUnhealthySecondThreshold: 900 # Config for the health check threshold for Ray Serve applications. Default value is 900.
  deploymentUnhealthySecondThreshold: 300 # Config for the health check threshold for Ray dashboard agent. Default value is 300.
  serveService:
    metadata:
      name: serve-amazon-light-gpt
      labels:
        custom-label: serve-amazon-light-gpt-label
      annotations:
        custom-annotation: serve-amazon-light-gpt-annotation
    spec:
      type: NodePort
      ports:
        - port: 8000
          nodePort: 32345
          name: serve-amazon-light-gpt-port
  serveConfig:
    importPath: ray_main.app
    runtimeEnv: |
      working_dir: "https://raw.githubusercontent.com/aiwantaozi/my-llm-frontend/main/my-llm-frontend.zip"
      pip:
        - gradio
  rayClusterConfig:
    rayVersion: "2.7.0" # should match the Ray version in the image of the containers
    ######################headGroupSpecs#################################
    # Ray head pod template.
    headGroupSpec:
      # The `rayStartParams` are used to configure the `ray start` command.
      # See https://github.com/ray-project/kuberay/blob/master/docs/guidance/rayStartParams.md for the default settings of `rayStartParams` in KubeRay.
      # See https://docs.ray.io/en/latest/cluster/cli.html#ray-start for all available options in `rayStartParams`.
      rayStartParams:
        dashboard-host: "0.0.0.0"
      #pod template
      template:
        spec:
          containers:
            - name: ray-head
              image: rayproject/ray:2.7.0
              env: 
              - name: MODEL_NAME
                value: amazon/LightGPT
              - name: BACKEND_URL
                value: "http://amazon-light-gpt-serve-svc:8000"
              resources:
                limits:
                  cpu: 1
                  memory: 1Gi
                requests:
                  cpu: 1
                  memory: 1Gi
              ports:
                - containerPort: 6379
                  name: gcs-server
                - containerPort: 8265 # Ray dashboard
                  name: dashboard
                - containerPort: 10001
                  name: client
                - containerPort: 8000
                  name: serve
    workerGroupSpecs:
      # the pod replicas in this group typed worker
      - replicas: 1
        minReplicas: 1
        maxReplicas: 5
        # logical group name, for this called small-group, also can be functional
        groupName: small-group
        # The `rayStartParams` are used to configure the `ray start` command.
        # See https://github.com/ray-project/kuberay/blob/master/docs/guidance/rayStartParams.md for the default settings of `rayStartParams` in KubeRay.
        # See https://docs.ray.io/en/latest/cluster/cli.html#ray-start for all available options in `rayStartParams`.
        rayStartParams: {}
        #pod template
        template:
          spec:
            containers:
              - name: ray-worker # must consist of lower case alphanumeric characters or '-', and must start and end with an alphanumeric character (e.g. 'my-name',  or '123-abc'
                image: rayproject/ray:2.7.0
                lifecycle:
                  preStop:
                    exec:
                      command: ["/bin/sh", "-c", "ray stop"]
                env: 
                - name: MODEL_NAME
                  value: test
                - name: BACKEND_URL
                  value: "http://192.168.0.9:1323"
                resources:
                  limits:
                    cpu: "500m"
                    memory: "1Gi"
                  requests:
                    cpu: "500m"
                    memory: "1Gi"
YAML
}