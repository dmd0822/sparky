targetScope = 'resourceGroup'

@description('Azure Container Registry name. Must be globally unique, lowercase, and alphanumeric.')
param registryName string

@description('Azure region for ACR.')
param location string = resourceGroup().location

@description('Tags applied to all resources.')
param tags object

@description('ACR SKU name.')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param skuName string = 'Basic'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

output registryName string = registry.name
output registryResourceId string = registry.id
output loginServer string = registry.properties.loginServer
