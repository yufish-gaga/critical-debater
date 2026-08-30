import { configureStore } from "@reduxjs/toolkit";
import debateReducer from "./slices/debateSlice";

export const store = configureStore({
  reducer: { debate: debateReducer },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
