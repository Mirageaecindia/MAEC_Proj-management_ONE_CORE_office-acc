import { Fragment } from 'react';

/** Breadcrumb, title, description, and optional right-hand controls (children). */
export function PageHeader({ breadcrumb = [], title, description, children }) {
  return (
    <div className="resource-heading-row">
      <div>
        <div className="breadcrumb">
          {breadcrumb.map((item, index) => (
            <Fragment key={`${item}-${index}`}>
              {index > 0 && <i>/</i>}
              {index === breadcrumb.length - 1 ? <strong>{item}</strong> : <span>{item}</span>}
            </Fragment>
          ))}
        </div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {children}
    </div>
  );
}
