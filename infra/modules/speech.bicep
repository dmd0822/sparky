targetScope = 'resourceGroup'

@description('Speech resource account name.')
param accountName string

@description('Azure region for Speech.')
param location string = resourceGroup().location

@description('Tags applied to all resources.')
param tags object

@description('Speech Services SKU name.')
param skuName string = 'S0'

@description('Custom subdomain name required for Entra ID auth.')
param customSubDomainName string = accountName

@description('Public network access setting for the Speech account.')
@allowed([
  'Enabled'
  'Disabled'
])
param publicNetworkAccess string = 'Enabled'

resource speech 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'SpeechServices'
  sku: {
    name: skuName
  }
  properties: {
    customSubDomainName: customSubDomainName
    disableLocalAuth: true
    publicNetworkAccess: publicNetworkAccess
  }
}

output accountName string = speech.name
output accountResourceId string = speech.id
output endpoint string = speech.properties.endpoint
