"""Export reviewed saved examples and aggregate results for the static website."""
import json
from pathlib import Path
import shutil

from recommend import load_model, recommend
from train_models import digest


def main():
    source, output = Path('data/raw'), Path('website')
    output.mkdir(exist_ok=True)
    model, transformer, plan = load_model(Path('data/processed'), Path('reports/test_plan.json'))
    audit = json.loads((source/'audit.json').read_text())
    catalog = json.loads((source/'problemset.json').read_text())
    splits = json.loads(Path('data/processed/splits.json').read_text())
    examples = []
    for handle in ['ethanxupro', 'BaJIuK', 'rahma_hisham925']:
        user = next(u for u in audit['users'] if u['handle'].casefold()==handle.casefold())
        path = source/'users'/f"{user['analysis_id']}.json"
        capture = json.loads(path.read_text())
        # Export every candidate in the same default difficulty window so filtering is real.
        result = recommend(capture, catalog['result']['problems'], model, transformer,
                           splits['validation_start'], limit=len(catalog['result']['problems']))
        result['capture_sha256'] = digest(path)
        examples.append(result)
        print(handle, result['evidence_rows'], len(result['recommendations']), flush=True)
    tests = json.loads(Path('reports/test_results.json').read_text())
    checks = json.loads(Path('reports/model_checks.json').read_text())
    data = {'examples':examples, 'tests':tests['splits'], 'selected':plan['selected'],
            'errors':checks['errors'], 'catalog_date':catalog['collected_at'],
            'provenance':{'model_sha256':plan['artifact_sha256'],
                          'catalog_sha256':digest(source/'problemset.json'),
                          'results_sha256':digest(Path('reports/test_results.json')),
                          'recommender_sha256':digest(Path('code/recommend.py')),
                          'exporter_sha256':digest(Path(__file__))}}
    (output/'data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    (output/'images').mkdir(exist_ok=True)
    for name in ['cohort_coverage.png','test_calibration.png']:
        shutil.copyfile(Path('reports/images')/name, output/'images'/name)
    (output/'.nojekyll').touch()


if __name__=='__main__':
    main()
