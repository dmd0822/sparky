@description('Azure region for the Log Analytics workspace.')
param location string

@description('Resource name for the workspace.')
param workspaceName string

@description('Retention in days for log data.')
param retentionInDays int = 30

@description('Standard tags applied to Azure resources.')
param tags object = {}

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    retentionInDays: retentionInDays
    sku: {
      name: 'PerGB2018'
    }
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output workspaceCustomerId string = workspace.properties.customerId
