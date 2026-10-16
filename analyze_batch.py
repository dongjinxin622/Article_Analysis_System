import pickle
import os

# 读取最新的批次结果
batch_dir = 'data/00. 研究课题/Article_Analysis_System_v3/batch_results/1f4b8e1b-532c-43'
batch_file = os.path.join(batch_dir, 'batch_1.pkl')

with open(batch_file, 'rb') as f:
    results = pickle.load(f)

# 查看结构和前几条数据
print('Total keys:', len(results))
print('Keys (first 5):', list(results.keys())[:5])

# 查看成功和失败的分布
success_count = 0
failed_count = 0
parse_issues = []
error_messages = []

for doi, result in results.items():
    if result.get('success'):
        success_count += 1
        data = result.get('data', {})
        related = data.get('related')
        if related not in [True, False]:
            parse_issues.append({
                'doi': doi,
                'related': related,
                'related_type': type(related).__name__ if related is not None else 'None',
                'data_keys': list(data.keys())[:10],
                'data_sample': str(data)[:300]
            })
    else:
        failed_count += 1
        error_messages.append({
            'doi': doi,
            'error': result.get('error', 'Unknown')
        })

print(f'\n=== Summary ===')
print(f'Success API calls: {success_count}, Failed API calls: {failed_count}')
print(f'Parse issues (related not True/False): {len(parse_issues)}')

# 显示几个具体的 API 失败原因
if error_messages:
    print('\n=== API Failed Examples ===')
    for err in error_messages[:5]:
        print(f"DOI: {err['doi']}")
        print(f"Error: {err['error']}")
        print()

# 显示几个具体的解析问题
if parse_issues:
    print('\n=== Parse Issues Examples ===')
    for issue in parse_issues[:3]:
        print(f"DOI: {issue['doi']}")
        print(f"related value: {issue['related']} (type: {issue['related_type']})")
        print(f"data keys: {issue['data_keys']}")
        print(f"data sample: {issue['data_sample'][:200]}")
        print()