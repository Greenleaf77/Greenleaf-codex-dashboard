export const USAGE_TABLE_PAGE_SIZE = 15;

export function paginateRows(rows, requestedPage, pageSize = USAGE_TABLE_PAGE_SIZE) {
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(Math.max(Number(requestedPage) || 1, 1), totalPages);
  const start = (page - 1) * pageSize;
  return {
    items: rows.slice(start, start + pageSize),
    page,
    totalPages
  };
}

export function truncateModelName(value, maxLength = 20) {
  const name = String(value ?? "");
  return name.length > maxLength ? `${name.slice(0, maxLength)}...` : name;
}
