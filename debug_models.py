from anthropic import Anthropic

client = Anthropic()

models = client.models.list()

print(models)
