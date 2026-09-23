/** "Project Name" dropdown used in page headers. */
export function ProjectSwitcher({ projects, value, onChange, disabled = false }) {
  return (
    <label className="project-switcher">
      <span>Project Name</span>
      <select
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || projects.length === 0}
      >
        {projects.length === 0 && <option value="">No projects</option>}
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.project_name}
          </option>
        ))}
      </select>
    </label>
  );
}
