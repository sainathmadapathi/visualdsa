import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut } from 'firebase/auth';
import { getFirestore, doc, setDoc, getDocs, collection } from 'firebase/firestore';

const configured = !!import.meta.env.VITE_FIREBASE_API_KEY && !!import.meta.env.VITE_FIREBASE_PROJECT_ID;
const firebase = configured ? initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}) : null;
export const auth = firebase ? getAuth(firebase) : null;
export const signIn = () => auth ? signInWithPopup(auth, new GoogleAuthProvider()) : Promise.reject(new Error('Configure Firebase in .env to enable sign-in.'));
export const logOut = () => auth ? signOut(auth) : Promise.resolve();
export async function syncLearning(problemId: string, data: Record<string, unknown>) {
  if (!auth?.currentUser || !firebase) return;
  await setDoc(doc(getFirestore(firebase), 'learners', auth.currentUser.uid, 'learning', problemId), { ...data, updatedAt: Date.now() }, { merge: true });
}
export async function cloudLearning() {
  if (!auth?.currentUser || !firebase) return [];
  const snapshot = await getDocs(collection(getFirestore(firebase), 'learners', auth.currentUser.uid, 'learning'));
  return snapshot.docs.map(d => ({ problemId: d.id, ...d.data() }));
}
