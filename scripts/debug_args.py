import sys, os, json
print('argv:', sys.argv)
print('PROMPT env:', os.environ.get('PROMPT'))
print('NEG_PROMPT env:', os.environ.get('NEG_PROMPT'))
print('VOLCENGINE_AK set?:', bool(os.environ.get('VOLCENGINE_AK')))
print('VOLCENGINE_SK set?:', bool(os.environ.get('VOLCENGINE_SK')))
