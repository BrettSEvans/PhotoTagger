import React, { useState, useEffect } from 'react';
import photoTaggerClient from '../api/photoTaggerClient';
import LoadingSpinner from '../components/LoadingSpinner';
import type { PhotoBatch } from '../types/index';

export const BatchesPage: React.FC = () => {
  const [batches, setBatches] = useState<PhotoBatch[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({
    team_name: '',
    team_year: 2026,
    tournament: '',
  });

  useEffect(() => {
    loadBatches();
  }, []);

  const loadBatches = async () => {
    setIsLoading(true);
    try {
      const data = await photoTaggerClient.getBatches();
      setBatches(data.batches || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load batches');
    } finally {
      setIsLoading(false);
    }
  };

  const startEdit = (batch: PhotoBatch) => {
    setEditingId(batch.id);
    setEditForm({
      team_name: batch.team_name || '',
      team_year: batch.team_year || 2026,
      tournament: batch.tournament || '',
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({ team_name: '', team_year: 2026, tournament: '' });
  };

  const saveEdit = async (batchId: number) => {
    try {
      await photoTaggerClient.updateBatch(batchId, editForm);
      setEditingId(null);
      await loadBatches();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update batch');
    }
  };

  const handleDelete = async (batchId: number) => {
    if (!window.confirm('Delete this batch? Photos will not be removed.')) return;
    try {
      await photoTaggerClient.deleteBatch(batchId);
      await loadBatches();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete batch');
    }
  };

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Import Batches</h1>
        <p className="text-slate-600 mb-6">Organize and tag groups of photos by import folder</p>

        {error && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 text-red-800 rounded-lg">
            {error}
          </div>
        )}

        {batches.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <p className="text-slate-600 mb-4">No import batches yet.</p>
            <p className="text-sm text-slate-500">Go to the Upload page to import photos from a folder.</p>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="w-full">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-slate-900">Folder</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-slate-900">Team</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-slate-900">Year</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-slate-900">Tournament</th>
                  <th className="px-6 py-3 text-center text-sm font-semibold text-slate-900">Photos</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-slate-900">Created</th>
                  <th className="px-6 py-3 text-right text-sm font-semibold text-slate-900">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {batches.map((batch) => (
                  <tr key={batch.id} className="hover:bg-slate-50">
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-slate-900 truncate" title={batch.source_folder}>
                        {batch.name || batch.source_folder.split('/').pop()}
                      </div>
                      <div className="text-xs text-slate-500 truncate">{batch.source_folder}</div>
                    </td>

                    {editingId === batch.id ? (
                      <>
                        <td className="px-6 py-4">
                          <input
                            type="text"
                            value={editForm.team_name}
                            onChange={(e) => setEditForm({ ...editForm, team_name: e.target.value })}
                            className="block w-full px-3 py-2 border border-slate-300 rounded-md text-sm"
                            placeholder="Team name"
                          />
                        </td>
                        <td className="px-6 py-4">
                          <input
                            type="number"
                            value={editForm.team_year}
                            onChange={(e) => setEditForm({ ...editForm, team_year: parseInt(e.target.value) })}
                            className="block w-full px-3 py-2 border border-slate-300 rounded-md text-sm"
                          />
                        </td>
                        <td className="px-6 py-4">
                          <input
                            type="text"
                            value={editForm.tournament}
                            onChange={(e) => setEditForm({ ...editForm, tournament: e.target.value })}
                            className="block w-full px-3 py-2 border border-slate-300 rounded-md text-sm"
                            placeholder="Tournament"
                          />
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-6 py-4 text-sm text-slate-700">{batch.team_name || '—'}</td>
                        <td className="px-6 py-4 text-sm text-slate-700">{batch.team_year || '—'}</td>
                        <td className="px-6 py-4 text-sm text-slate-700">{batch.tournament || '—'}</td>
                      </>
                    )}

                    <td className="px-6 py-4 text-center text-sm text-slate-900">{batch.photo_count}</td>
                    <td className="px-6 py-4 text-sm text-slate-600">
                      {new Date(batch.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      {editingId === batch.id ? (
                        <>
                          <button
                            onClick={() => saveEdit(batch.id)}
                            className="inline-flex items-center px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                          >
                            Save
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="inline-flex items-center px-3 py-1 bg-slate-200 text-slate-700 text-sm rounded hover:bg-slate-300"
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => startEdit(batch)}
                            className="inline-flex items-center px-3 py-1 text-blue-600 text-sm hover:bg-blue-50 rounded"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDelete(batch.id)}
                            className="inline-flex items-center px-3 py-1 text-red-600 text-sm hover:bg-red-50 rounded"
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
