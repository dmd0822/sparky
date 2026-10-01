targetScope = 'resourceGroup'

@description('Logical environment name. Dev and prod deploy into the same resource group with env-suffixed names.')
@allowed([
  'dev'
  'prod'
])
param environmentName string

@description('Azure region for all baseline resources.')
param location string = 'southcentralus'

@description('ACR name. Must be globally unique, lowercase, and alphanumeric.')
param acrName string

@description('Relay image. Code CD should override this with the built relay image.')
param relayImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Optional Foundry model deployment placeholders. Leave empty until South Central US model quota/version/deployment type are verified.')
param modelDeployments array = []

@description('Relay app registration identifier URI, for example api://<relay-app-id>. Entra app registrations are Microsoft Graph objects, so this value is created out of band and passed in at deploy time.')
param relayAudience string = ''

@description('Optional Pi-to-relay device-code scope. Defaults to <relayAudience>/.default when relayAudience is set.')
param relayDeviceScope string = ''

@description('Managed-identity scope used by the relay when calling Foundry.')
param foundryScope string = 'https://cognitiveservices.azure.com/.default'

@description('Managed-identity scope used by the relay when calling Speech.')
param speechScope string = 'https://cognitiveservices.azure.com/.default'

@description('Additional tags merged with required app/environment tags.')
param additionalTags object = {}

var tags = union(additionalTags, {
  app: 'sparky'
  environment: environmentName
})

var logAnalyticsWorkspaceName = 'sparky-law-${environmentName}'
var appInsightsName = 'sparky-appi-${environmentName}'
var containerAppsEnvironmentName = 'sparky-cae-${environmentName}'
var relayContainerAppName = 'sparky-relay-${environmentName}'
var aiServicesAccountName = 'sparky-ai-${environmentName}'
var foundryProjectName = 'sparky-proj-${environmentName}'
var speechAccountName = 'sparky-speech-${environmentName}'

module monitoring '../../modules/monitoring.bicep' = {
  name: 'monitoring-${environmentName}'
  params: {
    workspaceName: logAnalyticsWorkspaceName
    appInsightsName: appInsightsName
    location: location
    tags: tags
  }
}

module aiServices '../../modules/ai-services.bicep' = {
  name: 'ai-services-${environmentName}'
  params: {
    accountName: aiServicesAccountName
    projectName: foundryProjectName
    location: location
    tags: tags
    modelDeployments: modelDeployments
  }
}

module speech '../../modules/speech.bicep' = {
  name: 'speech-${environmentName}'
  params: {
    accountName: speechAccountName
    location: location
    tags: tags
  }
}

module acr '../../modules/container-registry.bicep' = {
  name: 'acr-${environmentName}'
  params: {
    registryName: acrName
    location: location
    tags: tags
  }
}

module containerAppsEnvironment '../../modules/container-app-environment.bicep' = {
  name: 'container-app-environment-${environmentName}'
  params: {
    environmentName: containerAppsEnvironmentName
    location: location
    tags: tags
    logAnalyticsWorkspaceResourceId: monitoring.outputs.workspaceResourceId
  }
}

module relay '../../modules/relay-container-app.bicep' = {
  name: 'relay-${environmentName}'
  params: {
    appName: relayContainerAppName
    location: location
    tags: tags
    managedEnvironmentId: containerAppsEnvironment.outputs.environmentResourceId
    image: relayImage
    // Only declare the registry when the image is actually served from it. The
    // relay's system identity does not exist until this module runs, so its
    // AcrPull grant in the rbac module below necessarily lands afterwards.
    // Declaring the registry on the baseline public-image deployment makes the
    // revision wait on a credential that cannot yet work, and it times out with
    // "Operation expired" roughly sixteen minutes later.
    acrLoginServer: startsWith(relayImage, '${acr.outputs.loginServer}/') ? acr.outputs.loginServer : ''
    azureTenantId: tenant().tenantId
    relayAudience: relayAudience
    relayDeviceScope: relayDeviceScope
    foundryScope: foundryScope
    speechScope: speechScope
    speechEndpoint: speech.outputs.endpoint
    speechResourceId: speech.outputs.accountResourceId
  }
}

module rbac '../../modules/rbac.bicep' = {
  name: 'rbac-${environmentName}'
  params: {
    relayPrincipalId: relay.outputs.principalId
    aiServicesAccountName: aiServices.outputs.accountName
    speechAccountName: speech.outputs.accountName
    acrName: acr.outputs.registryName
  }
}

output environmentName string = environmentName
output location string = location
output acrLoginServer string = acr.outputs.loginServer
output acrName string = acr.outputs.registryName
output acrResourceId string = acr.outputs.registryResourceId
output relayContainerAppName string = relay.outputs.appName
output relayContainerAppResourceId string = relay.outputs.appResourceId
output relayContainerAppIngressFqdn string = relay.outputs.ingressFqdn
output relayManagedIdentityPrincipalId string = relay.outputs.principalId
output relayUrl string = 'https://${relay.outputs.ingressFqdn}/api'
output tenantId string = tenant().tenantId
output containerAppsEnvironmentName string = containerAppsEnvironment.outputs.environmentName
output containerAppsEnvironmentResourceId string = containerAppsEnvironment.outputs.environmentResourceId
output aiServicesAccountName string = aiServices.outputs.accountName
output aiServicesAccountResourceId string = aiServices.outputs.accountResourceId
output aiServicesAccountEndpoint string = aiServices.outputs.accountEndpoint
output foundryProjectName string = aiServices.outputs.projectName
output foundryProjectResourceId string = aiServices.outputs.projectResourceId
output speechAccountName string = speech.outputs.accountName
output speechAccountResourceId string = speech.outputs.accountResourceId
output speechAccountEndpoint string = speech.outputs.endpoint
output logAnalyticsWorkspaceName string = monitoring.outputs.workspaceName
output logAnalyticsWorkspaceResourceId string = monitoring.outputs.workspaceResourceId
output applicationInsightsName string = monitoring.outputs.appInsightsName
output applicationInsightsResourceId string = monitoring.outputs.appInsightsResourceId
