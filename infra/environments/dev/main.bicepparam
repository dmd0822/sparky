using 'main.bicep'

param environmentName = 'dev'
param location = 'southcentralus'
param acrName = 'sparkyscrdev'
param relayImage = 'mcr.microsoft.com/k8se/quickstart:latest'
param modelDeployments = []
param additionalTags = {
  workload: 'sparky'
  lifecycle: 'development'
}
