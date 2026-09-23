import { describe, expect, it } from 'vitest';
import { ROOT_FOLDER_ID, findFolder, flattenFolders, folderPath, selectedFolderView } from './folderTree';

const TREE = [
  { id: 'a', name: '01_HVAC', children: [{ id: 'a1', name: 'Drawings', children: [] }] },
  { id: 'b', name: '02_Electrical', children: [] },
];

describe('folder tree helpers', () => {
  it('flattens depth-first with depth', () => {
    expect(flattenFolders(TREE).map((f) => [f.id, f.depth])).toEqual([
      ['a', 0],
      ['a1', 1],
      ['b', 0],
    ]);
  });

  it('finds nested folders and their path', () => {
    expect(findFolder(TREE, 'a1').name).toBe('Drawings');
    expect(findFolder(TREE, 'zzz')).toBeNull();
    expect(folderPath(TREE, 'a1').map((f) => f.name)).toEqual(['01_HVAC', 'Drawings']);
    expect(folderPath(TREE, 'zzz')).toEqual([]);
  });

  it('shows root files at the project root and falls back to root for unknown folders', () => {
    const mirror = { folder_hierarchy: TREE, files: [{ id: 'f1' }] };
    expect(selectedFolderView(mirror, ROOT_FOLDER_ID).files).toHaveLength(1);
    expect(selectedFolderView(mirror, 'a').files).toEqual([]);
    expect(selectedFolderView(mirror, 'missing').id).toBe(ROOT_FOLDER_ID);
    expect(selectedFolderView(undefined, 'a').files).toEqual([]);
  });
});
