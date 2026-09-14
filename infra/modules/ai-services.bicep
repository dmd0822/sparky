@description('Azure region for the AI services resources.')
param location string

@description('Azure OpenAI account name.')
param openAiAccountName string

@description('Azure Speech account name.')
param speechAccountName string

@description('Azure AI Content Safety account name.')
param contentSafetyAccountName string

@description('Standard tags applied to Azure resources.')
param tags object = {}

var openAiKind = 'OpenAI'
var speechKind = 'SpeechServices'
var contentSafetyKind = 'ContentSafety'

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAiAccountName
  location: location
  kind: openAiKind
  tags: tags
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAiAccountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

resource speechAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: speechAccountName
  location: location
  kind: speechKind
  tags: tags
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: speechAccountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

resource contentSafetyAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: contentSafetyAccountName
  location: location
  kind: contentSafetyKind
  tags: tags
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: contentSafetyAccountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

output openAiName string = openAiAccount.name
output openAiEndpoint string = openAiAccount.properties.endpoint
output openAiResourceId string = openAiAccount.id

output speechName string = speechAccount.name
output speechEndpoint string = speechAccount.properties.endpoint
output speechResourceId string = speechAccount.id

output contentSafetyName string = contentSafetyAccount.name
output contentSafetyEndpoint string = contentSafetyAccount.properties.endpoint
output contentSafetyResourceId string = contentSafetyAccount.id
