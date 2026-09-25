using 'main.bicep'

param environmentName = 'prod'
param location = 'southcentralus'
param acrName = 'sparkyscrprod'
param relayImage = 'mcr.microsoft.com/k8se/quickstart:latest'
param modelDeployments = []
param additionalTags = {
  workload: 'sparky'
  lifecycle: 'production'
}
