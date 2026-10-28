import { Route, Routes } from 'react-router-dom'
import { RequireAuth } from './auth/RequireAuth'
import { Layout } from './components/Layout'
import { Browse } from './pages/Browse'
import { ListingPage } from './pages/ListingPage'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { Register } from './pages/Register'
import { Sell } from './pages/Sell'
import { Verify } from './pages/Verify'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Public: browsing needs no account. */}
        <Route index element={<Browse />} />
        <Route path="listings/:id" element={<ListingPage />} />
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        {/* Signed-in only. Pages for selling and bidding will live here. */}
        <Route element={<RequireAuth />}>
          <Route path="sell" element={<Sell />} />
          <Route path="verify" element={<Verify />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
