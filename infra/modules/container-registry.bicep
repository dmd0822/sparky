@description('Azure region for the container registry.')
param location string

@description('Name of the Azure Container Registry.')
param registryName string

@description('Standard tags applied to Azure resources.')
param tags object = {}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    networkRuleSet: {
      defaultAction: 'Allow'
    }
    zoneRedundancy: 'Disabled'
  }
}

output registryName string = registry.name
output registryLoginServer string = registry.properties.loginServer
