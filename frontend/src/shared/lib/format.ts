export function formatDateTime(date: string | null | undefined) {
  if (!date) {
    return 'No data';
  }

  return new Date(date).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatCurrencyRub(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercent(value: number | null | undefined, digits = 1) {
  return `${Number(value ?? 0).toFixed(digits)}%`;
}

export function titleFromCode(value: string | null | undefined) {
  if (!value) {
    return 'Unclassified';
  }

  return value.replaceAll('_', ' ');
}
