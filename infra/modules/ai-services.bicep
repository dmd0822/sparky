targetScope = 'resourceGroup'

@description('Microsoft Foundry / Azure AI Services account name.')
param accountName string

@description('Foundry project child resource name.')
param projectName string

@description('Azure region for AI resources.')
param location string = resourceGroup().location

@description('Tags applied to all resources.')
param tags object

@description('AI Services SKU name.')
param skuName string = 'S0'

@description('Custom subdomain name required for Entra ID auth.')
param customSubDomainName string = accountName

@description('Public network access setting for the AI Services account.')
@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Enabled'

@description('Optional model deployments. Keep empty until regional model quota, deployment type, and model versions are confirmed.')
param modelDeployments array = []

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: skuName
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    // Required before the account will accept a Foundry project child resource.
    allowProjectManagement: true
    customSubDomainName: customSubDomainName
    disableLocalAuth: true
    publicNetworkAccess: publicNetworkAccess
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// Model deployment schema, regional capacity, and exact versions change frequently. Keep this array empty for M1 unless quota is verified immediately before deployment.
resource deployments 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = [for deployment in modelDeployments: {
  parent: account
  name: deployment.name
  sku: {
    name: deployment.?skuName ?? 'Standard'
    capacity: deployment.?capacity ?? 1
  }
  properties: {
    model: {
      format: deployment.modelFormat
      name: deployment.modelName
      version: deployment.?modelVersion ?? null
    }
    raiPolicyName: deployment.?raiPolicyName ?? null
  }
}]

output accountName string = account.name
output accountResourceId string = account.id
output accountEndpoint string = account.properties.endpoint
output projectName string = project.name
output projectResourceId string = project.id

