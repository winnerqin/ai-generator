import volcengine.visual.VisualService as vs

svc = vs.VisualService()
print('instance type:', type(svc))
methods = [m for m in dir(svc) if not m.startswith('_')]
print('methods count:', len(methods))
for m in methods:
    print(m)
