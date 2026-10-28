import { Route, Routes } from 'react-router-dom'
import { RequireAuth } from './auth/RequireAuth'
import { Layout } from './components/Layout'
import { Browse } from './pages/Browse'
import { ListingPage } from './pages/ListingPage'
import { EditListing } from './pages/EditListing'
import { ForgotPassword } from './pages/ForgotPassword'
import { Login } from './pages/Login'
import { MyBids } from './pages/MyBids'
import { MyListings } from './pages/MyListings'
import { NotFound } from './pages/NotFound'
import { Profile } from './pages/Profile'
import { Register } from './pages/Register'
import { Sell } from './pages/Sell'
import { Verify } from './pages/Verify'
import { Watchlist } from './pages/Watchlist'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Public: browsing needs no account. */}
        <Route index element={<Browse />} />
        <Route path="listings/:id" element={<ListingPage />} />
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
        {/* Signed-in only. Pages for selling and bidding will live here. */}
        <Route element={<RequireAuth />}>
          <Route path="sell" element={<Sell />} />
          <Route path="profile" element={<Profile />} />
          <Route path="listings/:id/edit" element={<EditListing />} />
          <Route path="my/listings" element={<MyListings />} />
          <Route path="my/bids" element={<MyBids />} />
          <Route path="verify" element={<Verify />} />
          <Route path="watchlist" element={<Watchlist />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
