import sys
sys.path.insert(0, '.')
from modules.ghost_detector import analyze_ghost_job

result = analyze_ghost_job('Shopify', 'We are looking for a rockstar ninja who thrives in a fast-paced environment with strong communication skills. Must be a team player.')
print('Score:', result['score'])
print('Verdict:', result['verdict'])
print('Red flags:', result['red_flags'])