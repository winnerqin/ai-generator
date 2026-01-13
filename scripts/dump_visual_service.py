import inspect
import itertools
import volcengine.visual.VisualService as vs

print('module:', vs)
print('\nmembers:')
print([m for m in dir(vs) if not m.startswith('_')])
print('\nsource (first 200 lines):')
src = inspect.getsource(vs)
for i, line in enumerate(itertools.islice(src.splitlines(), 0, 200), start=1):
    print(f'{i:03}: {line}')
