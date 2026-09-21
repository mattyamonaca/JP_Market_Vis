export async function loadDataset(fetchData, baseUrl, datasetId) {
  const directory = datasetId ? `data/${datasetId}/` : '';
  const read = async name => {
    const response = await fetchData(`${baseUrl}${directory}${name}`);
    if (!response.ok) throw new Error(`データを取得できませんでした (${response.status})`);
    return response.json();
  };
  const [companies, relations] = await Promise.all([
    read('M4_companies.json'), read('M5_company_relations.json'),
  ]);
  if (!companies.dataset_id || companies.dataset_id !== relations.dataset_id ||
      (datasetId && companies.dataset_id !== datasetId)) {
    throw new Error('データの更新中です。再読み込みしてください。');
  }
  return [companies, relations];
}
