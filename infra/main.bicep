targetScope = 'resourceGroup'

@description('Azure region for all deployed resources.')
param location string = resourceGroup().location

@description('Name of the target resource group. This can be set in the parameter file or pipeline config.')
param resourceGroupName string = resourceGroup().name

@description('Short environment identifier used in resource names.')
param environmentName string = 'dev'

@description('The image the broker container will run. Override for a real image in your registry.')
param brokerContainerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('The container port exposed by the broker service.')
param brokerContainerPort int = 8080

@description('Minimum broker replicas during normal operation.')
param minReplicas int = 1

@description('Maximum broker replicas during load spikes.')
param maxReplicas int = 2

var tags = {
  project: 'sparky'
  environment: environmentName
  resourceGroup: resourceGroupName
  managedBy: 'bicep'
  workload: 'broker'
}

var uniqueSuffix = uniqueString(resourceGroup().id, resourceGroupName, location, environmentName)
var workspaceName = 'law-${environmentName}-${uniqueSuffix}'
var managedEnvironmentName = 'cae-${environmentName}-${uniqueSuffix}'
var acrName = take(toLower('acr${uniqueSuffix}'), 50)
var openAiAccountName = 'sparky-openai-${environmentName}-${uniqueSuffix}'
var speechAccountName = 'sparky-speech-${environmentName}-${uniqueSuffix}'
var contentSafetyAccountName = 'sparky-content-safety-${environmentName}-${uniqueSuffix}'
var brokerAppName = 'sparky-broker-${environmentName}-${uniqueSuffix}'

module monitoring 'modules/log-analytics.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    workspaceName: workspaceName
    retentionInDays: 30
    tags: tags
  }
}

module registry 'modules/container-registry.bicep' = {
  name: 'registry'
  params: {
    location: location
    registryName: acrName
    tags: tags
  }
}

module aiServices 'modules/ai-services.bicep' = {
  name: 'ai-services'
  params: {
    location: location
    openAiAccountName: openAiAccountName
    speechAccountName: speechAccountName
    contentSafetyAccountName: contentSafetyAccountName
    tags: tags
  }
}

module brokerApp 'modules/broker-containerapp.bicep' = {
  name: 'broker-app'
  params: {
    location: location
    managedEnvironmentName: managedEnvironmentName
    brokerAppName: brokerAppName
    brokerImage: brokerContainerImage
    containerPort: brokerContainerPort
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    logAnalyticsWorkspaceName: monitoring.outputs.workspaceName
    registryLoginServer: registry.outputs.registryLoginServer
    registryName: registry.outputs.registryName
    openAiAccountName: aiServices.outputs.openAiName
    speechAccountName: aiServices.outputs.speechName
    contentSafetyAccountName: aiServices.outputs.contentSafetyName
    tags: tags
  }
}

output brokerAppName string = brokerApp.outputs.containerAppName
output brokerAppFqdn string = brokerApp.outputs.containerAppFqdn
output openAiEndpoint string = aiServices.outputs.openAiEndpoint
output speechEndpoint string = aiServices.outputs.speechEndpoint
output contentSafetyEndpoint string = aiServices.outputs.contentSafetyEndpoint
output containerRegistryLoginServer string = registry.outputs.registryLoginServer
output logAnalyticsWorkspaceName string = monitoring.outputs.workspaceName
