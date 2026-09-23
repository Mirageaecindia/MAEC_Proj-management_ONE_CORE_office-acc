/** Pure helpers over the mirror's nested folder hierarchy ({ id, name, children }). */

export const ROOT_FOLDER_ID = 'root';

/** Depth-first list of folders with their nesting depth, for the tree table. */
export function flattenFolders(folders = [], depth = 0) {
  return folders.flatMap((folder) => [{ ...folder, depth }, ...flattenFolders(folder.children, depth + 1)]);
}

export function findFolder(folders = [], folderId) {
  for (const folder of folders) {
    if (folder.id === folderId) return folder;
    const found = findFolder(folder.children, folderId);
    if (found) return found;
  }
  return null;
}

/** Folders from the top level down to `folderId` (empty when not found). */
export function folderPath(folders = [], folderId, trail = []) {
  for (const folder of folders) {
    const path = [...trail, { id: folder.id, name: folder.name }];
    if (folder.id === folderId) return path;
    const found = folderPath(folder.children, folderId, path);
    if (found.length) return found;
  }
  return [];
}

/** The folder being viewed; the project root carries the root-level files. */
export function selectedFolderView(mirror, folderId) {
  const root = { id: ROOT_FOLDER_ID, name: 'Project Root', files: mirror?.files ?? [] };
  if (!mirror || folderId === ROOT_FOLDER_ID) return root;
  const folder = findFolder(mirror.folder_hierarchy, folderId);
  // KNOWN (roadmap 3.6): the API does not list files inside subfolders yet.
  return folder ? { ...folder, files: folder.files ?? [] } : root;
}
