import json
import pathlib
from collections import Counter

recs = [json.loads(l) for l in open('data/fact_check_score_history.jsonl', encoding='utf-8') if l.strip()]
print('total records:', len(recs))
print('status:', Counter(r.get('status') for r in recs))
print('model:', Counter(r.get('gemini_model') for r in recs))

ok_paths = {r['path'] for r in recs if r.get('status') == 'ok'}
posts = {f'content/posts/{p.name}' for p in pathlib.Path('content/posts').glob('*.md')}
missing = sorted(posts - ok_paths)
print(f'\nexisting articles: {len(posts)}')
print(f'scored ok (unique): {len(ok_paths & posts)}')
print(f'NOT yet scored ok: {len(missing)}')
for m in missing[:15]:
    print('  ', m)
if len(missing) > 15:
    print(f'   ... and {len(missing)-15} more')
