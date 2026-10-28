import { createContext } from 'react'

// What the context provides (see AuthProvider):
//   user        the signed-in user ({ id, email, display_name, is_verified }) or null
//   loading     true while we hold a token but haven't yet learned who it belongs to
//   isSignedIn  whether a token is held
//   login(email, password) / register(email, displayName, password, { department, year_of_study })  -> { access_token, is_verified }
//   logout()    sign out and clear cached data
//   refreshUser()  re-fetch the profile, e.g. after verifying the email
//   updateProfile({ display_name, department, year_of_study })  -> the updated user
//   changePassword(current, next)  -> a fresh token (other devices are signed out)
export const AuthContext = createContext(null)
