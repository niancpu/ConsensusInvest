export function formatScore(value?: number | null): string {
  return typeof value === 'number' ? value.toFixed(2) : '-';
}

export function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function truncate(value: string, max: number): string {
  if (typeof value !== 'string') {
    return '-';
  }
  return value.length > max ? `${value.slice(0, max)}…` : value;
}
