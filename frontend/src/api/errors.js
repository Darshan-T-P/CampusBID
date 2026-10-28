import { ApiError } from './client'

/** A message safe to show a user for anything a request might throw. */
export function errorMessage(error) {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Please try again.'
}
