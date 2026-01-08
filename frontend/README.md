# Kingdom Auto Finance - Frontend

Modern React/Next.js frontend for the Kingdom Auto Finance accounting system.

## Prerequisites

- Node.js 18+ installed
- Backend FastAPI server running on port 8000

## Setup

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment Variables

Create a `.env.local` file:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` and set:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-random-secret-key
```

### 3. Run Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Login Credentials

**Password:** `Kingdom2025!$$`

(Same as the current Streamlit system)

## Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
frontend/
├── src/
│   ├── app/              # Next.js App Router pages
│   │   ├── login/        # Login page
│   │   ├── dashboard/    # Dashboard (coming soon)
│   │   └── layout.tsx    # Root layout
│   ├── components/       # Reusable React components
│   ├── lib/              # Utilities and API client
│   │   ├── api.ts        # FastAPI client
│   │   └── utils.ts      # Helper functions
│   └── types/            # TypeScript types
├── public/               # Static assets
└── package.json
```

## Features

### Phase 2.1 (Current)
- ✅ Login page
- ✅ API client connected to FastAPI
- ⏳ Dashboard (in progress)

### Phase 2.2 (Next)
- Payment Management page
- Reports with CSV export
- System Maintenance page

### Phase 3 (Future)
- NextAuth.js authentication
- Multi-user support
- Role-based access control
- Charts and visualizations
- Real-time job progress

## API Endpoints Used

All endpoints are from the FastAPI backend at `http://localhost:8000/api/v1`:

- `POST /payments/fetch` - Fetch payments from Google Sheets
- `POST /payments/process` - Process payments
- `GET /payments/log` - View payment log
- `POST /reports/*` - Generate various reports
- `POST /amortization/import` - Import schedules
- `GET /jobs/{job_id}` - Check job status

## Development Notes

- Uses Next.js 14 App Router
- TypeScript for type safety
- TailwindCSS for styling
- React Query for data fetching (coming soon)
- Zustand for state management (coming soon)

## Troubleshooting

### API Connection Issues

If you get connection errors:

1. Make sure FastAPI backend is running on port 8000
2. Check `NEXT_PUBLIC_API_URL` in `.env.local`
3. Verify CORS is enabled in FastAPI (already configured)

### Build Errors

If npm install fails:

```bash
rm -rf node_modules package-lock.json
npm install
```

## Next Steps

Continue to [PHASE2_STATUS.md](../PHASE2_STATUS.md) for implementation progress.
