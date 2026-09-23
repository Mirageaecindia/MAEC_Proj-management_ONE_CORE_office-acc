/** Contract currencies offered on Create Project. */
export const CURRENCIES = [
  { code: 'USD', symbol: '$' },
  { code: 'INR', symbol: '₹' },
  { code: 'EUR', symbol: '€' },
  { code: 'GBP', symbol: '£' },
  { code: 'AED', symbol: 'د.إ' },
  { code: 'AUD', symbol: 'A$' },
  { code: 'CAD', symbol: 'C$' },
  { code: 'SGD', symbol: 'S$' },
];

export function currencySymbol(code) {
  return CURRENCIES.find((currency) => currency.code === code)?.symbol || '$';
}

export function isSupportedCurrency(code) {
  return CURRENCIES.some((currency) => currency.code === code);
}
