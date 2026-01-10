# Design System Documentation

## Overview

This design system provides a comprehensive, maintainable approach to theming in the Kingdom Auto Finance Accounting System. By using semantic color tokens instead of hardcoded colors, we ensure consistency across light and dark modes while making future theme changes effortless.

### Philosophy

**Semantic Tokens Over Hardcoded Colors**: Instead of using specific color values (like `bg-white` or `text-gray-900`), we use semantic tokens that describe the *purpose* of the color (like `bg-card` or `text-foreground`). This approach:

- ✅ Automatically adapts to theme changes
- ✅ Ensures visual consistency
- ✅ Reduces maintenance overhead
- ✅ Improves accessibility
- ✅ Makes code more readable and self-documenting

### Benefits

1. **Maintainability**: Change theme colors in one place (globals.css), affects entire application
2. **Consistency**: All components use the same color palette
3. **Accessibility**: Ensure proper contrast ratios across all themes
4. **Developer Experience**: Clear, semantic naming makes code self-documenting
5. **Future-Proof**: Easy to add new themes or color schemes

---

## Theme Architecture

### ThemeContext

The application uses a React Context pattern for theme management:

**Location**: [src/contexts/ThemeContext.tsx](src/contexts/ThemeContext.tsx)

```typescript
type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  isLoading: boolean;
}
```

**Features**:
- Theme preference persisted to backend via `settingsAPI`
- Class-based dark mode (adds/removes 'dark' class on `<html>` element)
- `useTheme()` hook for components to access theme state
- Loading state while preference loads from backend

**Usage**:
```tsx
import { useTheme } from '@/contexts/ThemeContext';

function MyComponent() {
  const { theme, toggleTheme } = useTheme();

  return <button onClick={toggleTheme}>Toggle Theme</button>;
}
```

### CSS Variable System

**Location**: [src/app/globals.css](src/app/globals.css)

The design system uses CSS custom properties (variables) in HSL format for maximum flexibility:

```css
:root {
  --background: 0 0% 100%;      /* Light mode: white */
  --foreground: 222.2 84% 4.9%; /* Light mode: dark blue */
  /* ... more variables ... */
}

.dark {
  --background: 222.2 84% 4.9%; /* Dark mode: dark blue */
  --foreground: 210 40% 98%;    /* Dark mode: almost white */
  /* ... more variables ... */
}
```

### Tailwind Configuration

**Location**: [tailwind.config.ts](tailwind.config.ts)

Tailwind is configured to:
1. Use class-based dark mode: `darkMode: "class"`
2. Expose CSS variables as Tailwind color classes
3. Provide semantic color tokens

```typescript
colors: {
  border: "hsl(var(--border))",
  background: "hsl(var(--background))",
  foreground: "hsl(var(--foreground))",
  // ... more tokens ...
}
```

---

## Color Token Reference

### Complete Token Table

| Token | Usage | Light Mode | Dark Mode | Example |
|-------|-------|-----------|-----------|---------|
| `background` | Page background | White (hsl(0 0% 100%)) | Dark Blue (hsl(222.2 84% 4.9%)) | `bg-background` |
| `foreground` | Primary text on background | Dark Blue (hsl(222.2 84% 4.9%)) | Light (hsl(210 40% 98%)) | `text-foreground` |
| `card` | Card/panel backgrounds | White (hsl(0 0% 100%)) | Dark Blue (hsl(222.2 84% 4.9%)) | `bg-card` |
| `card-foreground` | Text on cards | Dark Blue (hsl(222.2 84% 4.9%)) | Light (hsl(210 40% 98%)) | `text-card-foreground` |
| `muted` | Muted backgrounds | Light Gray (hsl(210 40% 96.1%)) | Dark Gray (hsl(217.2 32.6% 17.5%)) | `bg-muted` |
| `muted-foreground` | Secondary/muted text | Medium Gray (hsl(215.4 16.3% 46.9%)) | Light Gray (hsl(215 20.2% 65.1%)) | `text-muted-foreground` |
| `border` | Borders, dividers | Light Gray (hsl(214.3 31.8% 91.4%)) | Dark Gray (hsl(217.2 32.6% 17.5%)) | `border-border` |
| `input` | Input field borders | Light Gray (hsl(214.3 31.8% 91.4%)) | Dark Gray (hsl(217.2 32.6% 17.5%)) | `border-input` |
| `primary` | Primary brand color | Dark Blue (hsl(222.2 47.4% 11.2%)) | Light (hsl(210 40% 98%)) | `bg-primary` |
| `primary-foreground` | Text on primary | Light (hsl(210 40% 98%)) | Dark Blue (hsl(222.2 47.4% 11.2%)) | `text-primary-foreground` |
| `secondary` | Secondary UI elements | Light Gray (hsl(210 40% 96.1%)) | Dark Gray (hsl(217.2 32.6% 17.5%)) | `bg-secondary` |
| `secondary-foreground` | Text on secondary | Dark Blue (hsl(222.2 47.4% 11.2%)) | Light (hsl(210 40% 98%)) | `text-secondary-foreground` |
| `accent` | Accent/highlight color | Light Gray (hsl(210 40% 96.1%)) | Dark Gray (hsl(217.2 32.6% 17.5%)) | `bg-accent` |
| `accent-foreground` | Text on accent | Dark Blue (hsl(222.2 47.4% 11.2%)) | Light (hsl(210 40% 98%)) | `text-accent-foreground` |
| `destructive` | Error/danger color | Red (hsl(0 84.2% 60.2%)) | Dark Red (hsl(0 62.8% 30.6%)) | `bg-destructive` |
| `destructive-foreground` | Text on destructive | Light (hsl(210 40% 98%)) | Light (hsl(210 40% 98%)) | `text-destructive-foreground` |
| `success` | Success state color | Green (hsl(142 76% 36%)) | Light Green (hsl(142 70% 45%)) | `bg-success` |
| `success-foreground` | Text on success | Light (hsl(355 100% 97%)) | Very Light Green (hsl(142 76% 96%)) | `text-success-foreground` |
| `success-muted` | Muted success background | Very Light Green (hsl(142 76% 96%)) | Dark Green (hsl(142 70% 15%)) | `bg-success-muted` |
| `success-muted-foreground` | Text on muted success | Dark Green (hsl(142 70% 25%)) | Light Green (hsl(142 70% 80%)) | `text-success-muted-foreground` |
| `warning` | Warning state color | Yellow (hsl(48 96% 53%)) | Light Yellow (hsl(48 96% 60%)) | `bg-warning` |
| `warning-foreground` | Text on warning | Dark Brown (hsl(26 83% 14%)) | Very Dark Yellow (hsl(48 96% 10%)) | `text-warning-foreground` |
| `warning-muted` | Muted warning background | Very Light Yellow (hsl(48 96% 95%)) | Dark Yellow (hsl(48 70% 15%)) | `bg-warning-muted` |
| `warning-muted-foreground` | Text on muted warning | Dark Yellow (hsl(32 81% 29%)) | Light Yellow (hsl(48 96% 80%)) | `text-warning-muted-foreground` |
| `info` | Info state color | Blue (hsl(221 83% 53%)) | Light Blue (hsl(221 83% 60%)) | `bg-info` |
| `info-foreground` | Text on info | Light (hsl(210 40% 98%)) | Very Dark Blue (hsl(221 83% 10%)) | `text-info-foreground` |
| `info-muted` | Muted info background | Very Light Blue (hsl(221 83% 96%)) | Dark Blue (hsl(221 70% 15%)) | `bg-info-muted` |
| `info-muted-foreground` | Text on muted info | Dark Blue (hsl(221 83% 20%)) | Light Blue (hsl(221 83% 80%)) | `text-info-muted-foreground` |

### When to Use Each Token

#### Layout & Structure
- **Page backgrounds**: `bg-background`
- **Cards, panels, modals**: `bg-card`
- **Table headers**: `bg-muted`
- **Dividers, borders**: `border-border`

#### Typography
- **Primary headings, body text**: `text-foreground` or `text-card-foreground`
- **Secondary text, descriptions**: `text-muted-foreground`
- **Labels on colored backgrounds**: Use corresponding foreground token

#### Interactive Elements
- **Primary buttons**: `bg-primary text-primary-foreground`
- **Secondary buttons**: `bg-secondary text-secondary-foreground`
- **Input fields**: `bg-card border-input text-foreground`
- **Focus states**: Use `ring-ring` for focus rings

#### Status Indicators
- **Success badges, notifications**: `bg-success-muted text-success-muted-foreground`
- **Warning badges, alerts**: `bg-warning-muted text-warning-muted-foreground`
- **Error messages, destructive actions**: `bg-destructive text-destructive-foreground`
- **Info messages, tooltips**: `bg-info-muted text-info-muted-foreground`

---

## Common Patterns & Examples

### Page Layouts

```tsx
// ✅ GOOD - Full page with semantic tokens
<main className="min-h-screen bg-background p-8">
  <div className="max-w-7xl mx-auto space-y-6">
    <h1 className="text-3xl font-bold text-foreground">Dashboard</h1>
    <p className="text-sm text-muted-foreground">Welcome back!</p>
  </div>
</main>

// ❌ BAD - Hardcoded colors
<main className="min-h-screen bg-white p-8">
  <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
  <p className="text-sm text-gray-600">Welcome back!</p>
</main>
```

### Cards and Panels

```tsx
// ✅ GOOD - Card with semantic tokens
<div className="bg-card p-6 rounded-lg shadow border border-border">
  <h2 className="text-lg font-semibold text-card-foreground mb-4">
    Summary
  </h2>
  <p className="text-sm text-muted-foreground">
    Your monthly report is ready.
  </p>
</div>

// ❌ BAD - Hardcoded colors
<div className="bg-white p-6 rounded-lg shadow">
  <h2 className="text-lg font-semibold text-gray-900 mb-4">Summary</h2>
  <p className="text-sm text-gray-600">Your monthly report is ready.</p>
</div>
```

### Form Inputs

```tsx
// ✅ GOOD - Input with semantic tokens
<div>
  <label className="block text-sm font-medium text-foreground mb-2">
    Email Address
  </label>
  <input
    type="email"
    className="w-full px-4 py-2 border border-input rounded-lg bg-card text-foreground focus:ring-2 focus:ring-ring focus:border-transparent"
    placeholder="you@example.com"
  />
</div>

// ❌ BAD - Hardcoded colors
<div>
  <label className="block text-sm font-medium text-gray-700 mb-2">
    Email Address
  </label>
  <input
    type="email"
    className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900"
    placeholder="you@example.com"
  />
</div>
```

### Status Badges

```tsx
// ✅ GOOD - Status badges with semantic tokens
<span className="px-3 py-1 rounded-full text-sm bg-success-muted text-success-muted-foreground">
  Completed
</span>

<span className="px-3 py-1 rounded-full text-sm bg-warning-muted text-warning-muted-foreground">
  Pending
</span>

<span className="px-3 py-1 rounded-full text-sm bg-info-muted text-info-muted-foreground">
  In Progress
</span>

<span className="px-3 py-1 rounded-full text-sm bg-destructive text-destructive-foreground">
  Failed
</span>

// ❌ BAD - Hardcoded colors without dark mode
<span className="px-3 py-1 rounded-full text-sm bg-green-100 text-green-800">
  Completed
</span>

<span className="px-3 py-1 rounded-full text-sm bg-yellow-100 text-yellow-800">
  Pending
</span>
```

### Data Tables

```tsx
// ✅ GOOD - Table with semantic tokens
<div className="bg-card rounded-lg shadow overflow-hidden border border-border">
  <table className="min-w-full divide-y divide-border">
    <thead className="bg-muted">
      <tr>
        <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
          Name
        </th>
        <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
          Status
        </th>
      </tr>
    </thead>
    <tbody className="bg-card divide-y divide-border">
      <tr className="hover:bg-muted/50 cursor-pointer">
        <td className="px-4 py-3 text-sm text-foreground">John Doe</td>
        <td className="px-4 py-3 text-sm text-muted-foreground">Active</td>
      </tr>
    </tbody>
  </table>
</div>

// ❌ BAD - Hardcoded colors
<table className="min-w-full">
  <thead className="bg-gray-50">
    <tr>
      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
        Name
      </th>
    </tr>
  </thead>
  <tbody className="bg-white divide-y divide-gray-200">
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-3 text-sm text-gray-900">John Doe</td>
    </tr>
  </tbody>
</table>
```

### Buttons and Interactive Elements

```tsx
// ✅ GOOD - Buttons with semantic tokens
<button className="px-6 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors">
  Primary Action
</button>

<button className="px-6 py-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-colors">
  Secondary Action
</button>

<button className="px-6 py-2 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition-colors">
  Delete
</button>

// ❌ BAD - Hardcoded colors
<button className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
  Primary Action
</button>

<button className="px-6 py-2 bg-gray-200 text-gray-900 rounded-lg hover:bg-gray-300">
  Secondary Action
</button>
```

---

## Migration Guide

### Converting Hardcoded to Semantic Tokens

#### Step 1: Identify Pattern

Look at the color usage and determine its semantic purpose:

- Is it a background? → Use `bg-*` tokens
- Is it text? → Use `text-*` tokens
- Is it a border? → Use `border-*` tokens
- What's the context? (card, page, muted area, status indicator)

#### Step 2: Replace with Appropriate Token

Common conversions:

| Hardcoded Class | Semantic Token | Notes |
|----------------|----------------|-------|
| `bg-white` | `bg-card` or `bg-background` | Use `bg-background` for page, `bg-card` for panels |
| `bg-gray-50` | `bg-muted` | For subtle background differences |
| `text-gray-900` | `text-foreground` | Primary text color |
| `text-gray-600` | `text-muted-foreground` | Secondary/subtitle text |
| `text-gray-500` | `text-muted-foreground` | Same as gray-600 |
| `border-gray-300` | `border-border` | All borders |
| `border-gray-200` | `border-border` | All borders |
| `bg-blue-100` (for info) | `bg-info-muted` | Status indicator |
| `bg-green-100` (for success) | `bg-success-muted` | Status indicator |
| `bg-yellow-100` (for warning) | `bg-warning-muted` | Status indicator |
| `bg-red-50` (for error) | `bg-destructive` | Error state |

### Before/After Examples

#### Example 1: Dashboard Card

```tsx
// BEFORE
<div className="bg-white p-6 rounded-lg shadow">
  <p className="text-sm font-medium text-gray-600">Total Sales</p>
  <p className="mt-2 text-3xl font-bold text-gray-900">$12,345</p>
</div>

// AFTER
<div className="bg-card p-6 rounded-lg shadow border border-border">
  <p className="text-sm font-medium text-muted-foreground">Total Sales</p>
  <p className="mt-2 text-3xl font-bold text-foreground">$12,345</p>
</div>
```

#### Example 2: Form Input

```tsx
// BEFORE
<input
  type="text"
  className="w-full px-4 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder-gray-500"
  placeholder="Enter name"
/>

// AFTER
<input
  type="text"
  className="w-full px-4 py-2 border border-input rounded-lg bg-card text-foreground placeholder:text-muted-foreground"
  placeholder="Enter name"
/>
```

#### Example 3: Status Badge

```tsx
// BEFORE
<span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm">
  Active
</span>

// AFTER
<span className="px-3 py-1 bg-success-muted text-success-muted-foreground rounded-full text-sm">
  Active
</span>
```

### Common Pitfalls to Avoid

1. **Don't Mix Approaches**
   ```tsx
   // ❌ BAD - Mixing semantic and hardcoded
   <div className="bg-card text-gray-900">

   // ✅ GOOD - Consistent semantic tokens
   <div className="bg-card text-card-foreground">
   ```

2. **Don't Use dark: Prefix for Neutral Colors**
   ```tsx
   // ❌ BAD - Unnecessary dark: variants
   <div className="bg-white dark:bg-gray-800 text-gray-900 dark:text-white">

   // ✅ GOOD - Let semantic tokens handle it
   <div className="bg-card text-card-foreground">
   ```

3. **Don't Forget Borders**
   ```tsx
   // ❌ BAD - Hardcoded border won't show in dark mode
   <div className="bg-card border border-gray-200">

   // ✅ GOOD - Border visible in both modes
   <div className="bg-card border border-border">
   ```

4. **Don't Hardcode Placeholder Colors**
   ```tsx
   // ❌ BAD
   <input className="placeholder-gray-500" />

   // ✅ GOOD
   <input className="placeholder:text-muted-foreground" />
   ```

---

## Component Checklist

Use this checklist when creating or updating components to ensure dark mode compatibility:

### Dark Mode Ready Criteria

- [ ] No hardcoded color classes (`bg-white`, `text-gray-900`, etc.)
- [ ] All backgrounds use semantic tokens (`bg-card`, `bg-muted`, etc.)
- [ ] All text uses semantic tokens (`text-foreground`, `text-muted-foreground`, etc.)
- [ ] All borders use semantic tokens (`border-border`, `border-input`, etc.)
- [ ] Status indicators use appropriate status tokens (`bg-success-muted`, etc.)
- [ ] Hover states adapt to theme
- [ ] Focus states visible in both modes
- [ ] Placeholders use `placeholder:text-muted-foreground`
- [ ] Component tested in both light and dark modes
- [ ] Text remains readable in both modes (sufficient contrast)

### Quick Verification

**Visual Test**:
1. View component in light mode
2. Toggle to dark mode (Maintenance page → Theme toggle)
3. Verify:
   - No white blocks appearing
   - All text is readable
   - Borders are visible
   - Colors maintain their semantic meaning
   - No harsh contrast issues

---

## Testing Guidelines

### Manual Testing Steps

1. **Navigate to Maintenance Page**
   - Find the theme toggle switch
   - Note current theme

2. **Test Each Page**
   - Dashboard
   - Payments
   - Reports
   - Amortization
   - Login
   - Maintenance

3. **For Each Page, Verify**:
   - [ ] All backgrounds properly colored
   - [ ] All text readable (no black text on dark backgrounds)
   - [ ] Borders visible
   - [ ] Cards/panels have proper contrast
   - [ ] Form inputs visible with clear borders
   - [ ] Status badges/indicators readable
   - [ ] Hover states work
   - [ ] Focus states visible

4. **Toggle Theme and Repeat**
   - Verify smooth transition
   - Check all elements update correctly

### Visual Verification Checklist

#### Light Mode
- [ ] White/light backgrounds on cards
- [ ] Dark text on light backgrounds
- [ ] Subtle borders visible
- [ ] Colored status indicators bright and clear

#### Dark Mode
- [ ] Dark backgrounds on everything
- [ ] Light text on dark backgrounds
- [ ] Borders visible but not harsh
- [ ] Colored status indicators muted but distinguishable

### Cross-Browser Testing

Test in multiple browsers to ensure consistency:
- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari (if on macOS)

### Accessibility Testing

Verify proper contrast ratios:
- Use browser DevTools or tools like [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- Ensure WCAG AA compliance (4.5:1 for normal text, 3:1 for large text)
- Test with keyboard navigation
- Verify focus indicators visible in both modes

---

## Future Enhancements

### 1. Additional Theme Options

The current architecture supports adding more themes beyond light/dark:

```css
.blue-theme {
  --background: /* blue variant */;
  --foreground: /* blue variant */;
  /* ... */
}

.high-contrast {
  --background: 0 0% 0%;        /* Pure black */
  --foreground: 0 0% 100%;      /* Pure white */
  /* ... maximum contrast values */
}
```

### 2. System Preference Detection

Auto-detect user's OS theme preference on first visit:

```typescript
// In ThemeContext.tsx
useEffect(() => {
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    setTheme('dark');
  }
}, []);
```

### 3. Per-Component Theme Overrides

For special cases, allow components to override theme locally:

```tsx
<div data-theme="dark">
  {/* This section always dark, regardless of global theme */}
</div>
```

### 4. Theme Preview

Add a preview mode to test all components in different themes simultaneously.

### 5. Accessibility Improvements

- Add reduced motion support
- High contrast mode
- Larger text options
- Color blind friendly palettes

### 6. Component Library

Extract themed components into a shared library for reuse across projects:

```tsx
import { Card, Button, Input } from '@/components/ui';

// All components automatically theme-aware
```

---

## Resources

### Internal References
- [ThemeContext Implementation](src/contexts/ThemeContext.tsx)
- [CSS Variables Definition](src/app/globals.css)
- [Tailwind Configuration](tailwind.config.ts)
- [Implementation Plan](/Users/gustavocamilo/.claude/plans/humble-knitting-grove.md)

### External Resources
- [Tailwind CSS Dark Mode](https://tailwindcss.com/docs/dark-mode)
- [CSS Custom Properties (MDN)](https://developer.mozilla.org/en-US/docs/Web/CSS/Using_CSS_custom_properties)
- [WCAG Color Contrast](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)
- [shadcn/ui Theming](https://ui.shadcn.com/docs/theming) (our design system is inspired by shadcn)

---

## Questions?

If you have questions about implementing the design system or need clarification on token usage:

1. Check the "Common Patterns & Examples" section above
2. Review the "Migration Guide" for before/after comparisons
3. Use the "Component Checklist" to verify your implementation
4. Test in both light and dark modes before considering it complete

Remember: **When in doubt, use semantic tokens!** They're designed to handle theming automatically.
