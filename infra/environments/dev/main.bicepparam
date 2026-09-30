using 'main.bicep'

param environmentName = 'dev'
param location = 'southcentralus'
param acrName = 'sparkyscrdev'
param relayImage = 'mcr.microsoft.com/k8se/quickstart:latest'
param relayDeviceScope = ''
param foundryScope = 'https://cognitiveservices.azure.com/.default'
param speechScope = 'https://cognitiveservices.azure.com/.default'
param modelDeployments = []
param additionalTags = {
  workload: 'sparky'
  lifecycle: 'development'
}
