targetScope = 'resourceGroup'

@description('Container Apps managed environment name.')
param environmentName string

@description('Azure region for the managed environment.')
param location string = resourceGroup().location

@description('Tags applied to all resources.')
param tags object

@description('Log Analytics workspace resource ID for Container Apps diagnostic settings.')
param logAnalyticsWorkspaceResourceId string

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'azure-monitor'
    }
    zoneRedundant: false
  }
}

resource managedEnvironmentDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'container-apps-logs'
  scope: managedEnvironment
  properties: {
    workspaceId: logAnalyticsWorkspaceResourceId
    logs: [
      {
        category: 'ContainerAppConsoleLogs'
        enabled: true
      }
      {
        category: 'ContainerAppSystemLogs'
        enabled: true
      }
    ]
    metrics: []
  }
}

output environmentName string = managedEnvironment.name
output environmentResourceId string = managedEnvironment.id
output defaultDomain string = managedEnvironment.properties.defaultDomain
