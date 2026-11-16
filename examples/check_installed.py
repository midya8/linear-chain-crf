"""Check the installed tests and full CLI outputs outside the checkout.

Use --section tests or --section commands to run either half on its own.
The default runs both. These are same-runtime packaging comparisons, not
independent numerical or statistical evidence.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()
ENV.pop('PYTHONPATH', None)
ENV.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
MODULES = ['taglab', 'taglab.__main__', 'taglab.core', 'taglab.model',
           'taglab.fixture', 'taglab.experiment', 'taglab.export',
           'taglab.normalization', 'taglab.conditioning', 'taglab.sampling',
           'taglab.counts']
COMMANDS = [
    ['demo'], ['normalization'], ['train', '--output', 'fresh.json'],
    ['audit'], ['audit', '--input', 'fresh.json'],
    ['infer', '--symbols', '[-2,0,2]', '--family', 'chain'],
    ['infer', '--symbols', '[1]', '--family', 'local'],
    ['condition', '--symbols', '[0,1]', '--allowed', '[[0],[0,1,2]]'],
    ['condition', '--symbols', '[0,1]', '--allowed', '[[],[0,1,2]]'],
    ['condition', '--symbols', '[0,1]', '--allowed', '[[0,1,2],[0,1,2]]', '--family', 'local'],
    ['sample', '--symbols', '[0,1]', '--allowed', '[[0,1,2],[0,1,2]]', '--seed', '17'],
    ['sample', '--symbols', '[0,1]', '--allowed', '[[0,1,2],[0,1,2]]', '--uniforms', '[0.2,0.7]', '--mode', 'independent'],
    ['count', '--symbols', '[0,1,2]', '--label', '0', '--count', '1'],
    ['count', '--symbols', '[0,1]', '--label', '2', '--count', '0', '--family', 'local'],
    ['export', '--output', 'web'],
]
EXPORTS = ['archive-0.js', 'archive-1.js', 'archive-2.js', 'data.js']


def call(args, cwd, env=ENV):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--section', choices=['all', 'tests', 'commands'], default='all')
args = parser.parse_args()
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    wheels = work / 'wheels'
    wheels.mkdir()
    call([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '-w', str(wheels), str(ROOT)], work)
    built = list(wheels.glob('*.whl'))
    assert len(built) == 1, built
    venv.create(work / 'env', with_pip=True)
    py = str(work / 'env/bin/python')
    call([py, '-m', 'pip', 'install', str(built[0])], work)
    outside = work / 'outside'
    outside.mkdir()
    for name in ['tests', 'examples', 'docs']:
        shutil.copytree(ROOT / name, outside / name)
    suite = '''
import importlib,importlib.util,json,pathlib,sys,unittest
outside=pathlib.Path.cwd().resolve()
sys.path.insert(0,str(outside))
names=json.loads(sys.argv[1])
source=pathlib.Path(sys.argv[2]).resolve()
prefix=pathlib.Path(sys.prefix).resolve()
for name in names:importlib.import_module(name)
def check():
    for name in names:
        origin=pathlib.Path(importlib.util.find_spec(name).origin).resolve()
        assert origin.is_relative_to(prefix),(name,str(origin))
        assert not origin.is_relative_to(source),(name,str(origin))
        assert 'site-packages' in origin.parts,(name,str(origin))
check()
if sys.argv[3]=='tests':
    tests=unittest.defaultTestLoader.discover(str(outside/'tests'))
    result=unittest.TextTestRunner(verbosity=2).run(tests)
    assert result.testsRun>0 and result.wasSuccessful()
    print(json.dumps(dict(tests=result.testsRun)))
check()
print(json.dumps(dict(installed_origins=len(names),checked_before_and_after=True)))
'''
    if args.section in ['all', 'tests']:
        print(call([py, '-I', '-c', suite, json.dumps(MODULES), str(ROOT), 'tests'], outside))
    if args.section in ['all', 'commands']:
        print(call([py, '-I', '-c', suite, json.dumps(MODULES), str(ROOT), 'imports'], outside))
        reference = work / 'reference'
        reference.mkdir()
        source_env = ENV.copy()
        source_env['PYTHONPATH'] = str(ROOT)
        expected = []
        for command in COMMANDS:
            output = call([sys.executable, '-m', 'taglab'] + command, reference, source_env).strip()
            expected.append(output)
        fresh = json.loads((reference / 'fresh.json').read_text())
        exports = {name: (reference / 'web' / name).read_bytes() for name in EXPORTS}
        for name, data in exports.items():
            assert data == (ROOT / 'docs' / name).read_bytes(), name
        # This package has no console-script entrypoint. Check its module CLI.
        for command, report in zip(COMMANDS, expected):
            output = call([py, '-I', '-m', 'taglab'] + command, outside).strip()
            assert output == report, command
        assert json.loads((outside / 'fresh.json').read_text()) == fresh
        for name, data in exports.items():
            assert (outside / 'web' / name).read_bytes() == data, name
        print(call([py, '-I', '-c', suite, json.dumps(MODULES), str(ROOT), 'imports'], outside))
        print(json.dumps(dict(command_invocations=len(COMMANDS), command_kinds=9,
                              complete_output_files=5, fresh_models=6, entrypoints=1)))
