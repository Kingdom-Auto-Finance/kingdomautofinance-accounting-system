/**
 * Type definitions for amortization schedule data and related structures
 */

export interface Loan {
  loan_id: string;
  customer_name?: string;
  vehicle_info?: string;
  loan_amount?: number;
  created_at?: string;
}

export interface ScheduleRow {
  paymentnumber: number;
  duedate: string;
  scheduledbalance: number;
  adjustedbalance: number;
  scheduledpayment: number;
  actualpaymentamount: number | null;
  actualpaymentdate: string | null;
  scheduledprincipal: number;
  scheduledinterest: number;
  principalpaid: number | null;
  interestpaid: number | null;
  latefee: number | null;
  creditapplied: number | null;
  scheduledfinalbalance: number;
  endingbalance: number;
  status: string;
}

export interface ColumnDefinition {
  key: keyof ScheduleRow;
  label: string;
  category: 'dates' | 'balances' | 'scheduled' | 'actual' | 'fees' | 'status';
  isDefault: boolean;
  format?: 'currency' | 'date' | 'number' | 'text';
  description?: string;
}

export const COLUMN_DEFINITIONS: ColumnDefinition[] = [
  // Dates
  {
    key: 'paymentnumber',
    label: 'Payment #',
    category: 'dates',
    isDefault: true,
    format: 'number',
    description: 'Payment installment number'
  },
  {
    key: 'duedate',
    label: 'Due Date',
    category: 'dates',
    isDefault: true,
    format: 'date',
    description: 'Scheduled payment due date'
  },
  {
    key: 'actualpaymentdate',
    label: 'Payment Date',
    category: 'dates',
    isDefault: true,
    format: 'date',
    description: 'Actual date payment was received'
  },

  // Balances
  {
    key: 'scheduledbalance',
    label: 'Scheduled Balance',
    category: 'balances',
    isDefault: false,
    format: 'currency',
    description: 'Expected balance at start of period'
  },
  {
    key: 'adjustedbalance',
    label: 'Adjusted Balance',
    category: 'balances',
    isDefault: false,
    format: 'currency',
    description: 'Balance adjusted for payments'
  },
  {
    key: 'scheduledfinalbalance',
    label: 'Expected End Balance',
    category: 'balances',
    isDefault: false,
    format: 'currency',
    description: 'Expected balance after payment'
  },
  {
    key: 'endingbalance',
    label: 'Ending Balance',
    category: 'balances',
    isDefault: true,
    format: 'currency',
    description: 'Actual ending balance after payment'
  },

  // Scheduled amounts
  {
    key: 'scheduledpayment',
    label: 'Scheduled Payment',
    category: 'scheduled',
    isDefault: true,
    format: 'currency',
    description: 'Expected payment amount'
  },
  {
    key: 'scheduledprincipal',
    label: 'Scheduled Principal',
    category: 'scheduled',
    isDefault: false,
    format: 'currency',
    description: 'Expected principal portion'
  },
  {
    key: 'scheduledinterest',
    label: 'Scheduled Interest',
    category: 'scheduled',
    isDefault: false,
    format: 'currency',
    description: 'Expected interest portion'
  },

  // Actual amounts
  {
    key: 'actualpaymentamount',
    label: 'Actual Payment',
    category: 'actual',
    isDefault: true,
    format: 'currency',
    description: 'Actual payment amount received'
  },
  {
    key: 'principalpaid',
    label: 'Principal Paid',
    category: 'actual',
    isDefault: false,
    format: 'currency',
    description: 'Actual principal portion paid'
  },
  {
    key: 'interestpaid',
    label: 'Interest Paid',
    category: 'actual',
    isDefault: false,
    format: 'currency',
    description: 'Actual interest portion paid'
  },

  // Fees and credits
  {
    key: 'latefee',
    label: 'Late Fee',
    category: 'fees',
    isDefault: true,
    format: 'currency',
    description: 'Late fee assessed'
  },
  {
    key: 'creditapplied',
    label: 'Credit Applied',
    category: 'fees',
    isDefault: false,
    format: 'currency',
    description: 'Credits applied to payment'
  },

  // Status
  {
    key: 'status',
    label: 'Status',
    category: 'status',
    isDefault: true,
    format: 'text',
    description: 'Payment status'
  },
];

export const DEFAULT_VISIBLE_COLUMNS = new Set(
  COLUMN_DEFINITIONS.filter((col) => col.isDefault).map((col) => col.key)
);

export const COLUMN_CATEGORIES = [
  { id: 'dates', label: 'Dates', icon: '📅' },
  { id: 'balances', label: 'Balances', icon: '💰' },
  { id: 'scheduled', label: 'Scheduled Amounts', icon: '📋' },
  { id: 'actual', label: 'Actual Amounts', icon: '✅' },
  { id: 'fees', label: 'Fees & Credits', icon: '💵' },
  { id: 'status', label: 'Status', icon: '📊' },
] as const;

export interface ValidationResult {
  isValid: boolean;
  expected: number;
  actual: number;
  diff: number;
}

export interface PaymentValidation {
  allocationCheck: ValidationResult;
  balanceCheck: ValidationResult;
}
